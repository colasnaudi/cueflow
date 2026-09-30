"""Genre review queue: approve, reject or reset suggestions. Only the catalogue changes, never the files."""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import GenreReview, GenreSuggestion, Track
from app.services.queries import folder_filter

ReviewStatus = Literal["PENDING", "APPROVED", "REJECTED"]
Action = Literal["approve", "reject", "reset"]


class ReviewError(ValueError):
    pass


def counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(GenreReview.status, func.count()).group_by(GenreReview.status)).all()
    return {"PENDING": 0, "APPROVED": 0, "REJECTED": 0} | dict(rows)


def suggestions_for(session: Session, track_id: uuid.UUID) -> list[GenreSuggestion]:
    return list(
        session.scalars(
            select(GenreSuggestion).where(GenreSuggestion.track_id == track_id).order_by(GenreSuggestion.rank)
        )
    )


def list_reviews(
    session: Session, status: ReviewStatus, folder: str | None, limit: int, offset: int
) -> tuple[list[tuple[Track, GenreReview]], int]:
    query = (
        select(Track, GenreReview)
        .join(GenreReview, GenreReview.track_id == Track.id)
        .where(GenreReview.status == status)
    )
    if folder:
        query = query.where(folder_filter(folder))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    ordering = (Track.path,) if status == "PENDING" else (GenreReview.reviewed_at.desc(),)
    rows = session.execute(query.order_by(*ordering).limit(limit).offset(offset)).all()
    return [(track, review) for track, review in rows], total


def set_genre(session: Session, track: Track, genre: str | None) -> None:
    """Identical copies of the file get the same genre: only one of them was analysed."""
    for copy in session.scalars(select(Track).where(Track.file_hash == track.file_hash)):
        copy.genre = genre


def apply(
    session: Session, track: Track, review: GenreReview, action: Action, genre: str | None = None
) -> None:
    if action == "approve":
        genre = (genre or "").strip()
        if not genre:
            raise ReviewError("genre is required to approve")
        if review.status != "APPROVED":
            review.previous_genre = track.genre
        review.status, review.chosen_genre, review.reviewed_at = "APPROVED", genre, datetime.now()
        set_genre(session, track, genre)
        return

    # reject / reset: an approved genre is undone, the original one comes back.
    if review.status == "APPROVED":
        set_genre(session, track, review.previous_genre)
    if action == "reject":
        review.status, review.chosen_genre, review.reviewed_at = "REJECTED", None, datetime.now()
    else:
        review.status, review.chosen_genre, review.reviewed_at = "PENDING", None, None


def bulk_approve(session: Session, track_ids: list[uuid.UUID]) -> int:
    """Approve the top suggestion of each pending track."""
    approved = 0
    for track_id in track_ids:
        track, review = session.get(Track, track_id), session.get(GenreReview, track_id)
        top = next(iter(suggestions_for(session, track_id)), None)
        if track and review and top and review.status == "PENDING":
            apply(session, track, review, "approve", top.genre)
            approved += 1
    return approved
