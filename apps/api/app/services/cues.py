"""Cue storage: analysis suggestions are replaced on re-analysis, approved or user cues never are."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Cue, Track
from app.services.cue_engine import PlannedCue


def cues_of(session: Session, track_id: uuid.UUID) -> list[Cue]:
    return list(session.scalars(select(Cue).where(Cue.track_id == track_id).order_by(Cue.type, Cue.slot)))


def replace_suggestions(session: Session, track_id: uuid.UUID, planned: list[PlannedCue]) -> None:
    kept = {
        c.slot
        for c in session.scalars(select(Cue).where(Cue.track_id == track_id))
        if c.approved or c.source == "USER"
    }
    session.execute(
        delete(Cue).where(Cue.track_id == track_id, Cue.source == "ANALYSIS", Cue.approved.is_(False))
    )
    for cue in planned:
        if cue.slot not in kept:
            session.add(Cue(track_id=track_id, source="ANALYSIS", **cue.as_dict()))


def _copies(session: Session, track: Track) -> list[Track]:
    return list(session.scalars(select(Track).where(Track.file_hash == track.file_hash)))


def approve(session: Session, track: Track) -> int:
    """The DJ validated the cues of this file (every identical copy)."""
    count = 0
    for copy in _copies(session, track):
        for cue in cues_of(session, copy.id):
            count += not cue.approved
            cue.approved = True
    return count


def remove(session: Session, track: Track, cue_id: uuid.UUID) -> bool:
    cue = session.get(Cue, cue_id)
    if cue is None or cue.track_id != track.id:
        return False
    session.execute(
        delete(Cue).where(Cue.slot == cue.slot, Cue.track_id.in_([c.id for c in _copies(session, track)]))
    )
    return True
