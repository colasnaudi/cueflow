import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import GenreReview, Track
from app.schemas import BulkApprove, ReviewAction, ReviewItem, ReviewPage
from app.services import genres, review
from app.services.cleanup import relative_folder

router = APIRouter(tags=["review"])


def review_item(session: Session, track: Track, state: GenreReview) -> ReviewItem:
    return ReviewItem(
        track=track,
        folder=relative_folder(track.path),
        suggestions=review.suggestions_for(session, track.id),
        review=state,
    )


@router.get("/review/genres", response_model=ReviewPage)
def list_reviews(
    status: review.ReviewStatus = "PENDING",
    folder: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    rows, total = review.list_reviews(session, status, folder, limit, offset)
    return ReviewPage(
        items=[review_item(session, track, state) for track, state in rows],
        total=total,
        counts=review.counts(session),
    )


@router.post("/review/genres/bulk-approve")
def bulk_approve(body: BulkApprove, session: Session = Depends(get_session)):
    approved = review.bulk_approve(session, body.track_ids)
    session.commit()
    return {"approved": approved, "counts": review.counts(session)}


@router.post("/review/genres/{track_id}", response_model=ReviewItem)
def review_genre(track_id: uuid.UUID, body: ReviewAction, session: Session = Depends(get_session)):
    track, state = session.get(Track, track_id), session.get(GenreReview, track_id)
    if track is None or state is None:
        raise HTTPException(404, "No genre review for this track")
    try:
        review.apply(session, track, state, body.action, body.genre)
    except review.ReviewError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    session.refresh(track)
    return review_item(session, track, state)


@router.get("/analysis/genres")
def analysis_status():
    return genres.status.as_dict()


@router.post("/analysis/genres", status_code=202)
def start_analysis(limit: int | None = Query(default=None, ge=1)):
    try:
        genres.start_in_background(limit)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"started": True}


@router.post("/analysis/genres/stop")
def stop_analysis():
    genres.request_stop()
    return genres.status.as_dict()
