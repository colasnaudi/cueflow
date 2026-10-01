"""Cue storage: generated cues are replaced on re-analysis; cues validated or made by the DJ never are.

With AUTO_APPROVE_CUES (default) generated cues are approved immediately (approved_by AUTO), so a library
analysis leaves every track ready for the Rekordbox export.
"""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Cue, Track
from app.services.cue_engine import PlannedCue


def cues_of(session: Session, track_id: uuid.UUID) -> list[Cue]:
    return list(session.scalars(select(Cue).where(Cue.track_id == track_id).order_by(Cue.type, Cue.slot)))


def _validated(cue: Cue) -> bool:
    return cue.source == "USER" or cue.approved_by == "USER"


def replace_suggestions(session: Session, track_id: uuid.UUID, planned: list[PlannedCue]) -> None:
    kept = {c.slot for c in session.scalars(select(Cue).where(Cue.track_id == track_id)) if _validated(c)}
    session.execute(
        delete(Cue).where(
            Cue.track_id == track_id, Cue.source == "ANALYSIS", Cue.approved_by.is_distinct_from("USER")
        )
    )
    auto = get_settings().auto_approve_cues
    for cue in planned:
        if cue.slot not in kept:
            session.add(
                Cue(
                    track_id=track_id,
                    source="ANALYSIS",
                    approved=auto,
                    approved_by="AUTO" if auto else None,
                    **cue.as_dict(),
                )
            )


def auto_approve_pending(session: Session) -> int:
    """Cues generated before auto-approval was on become approved (AUTO)."""
    if not get_settings().auto_approve_cues:
        return 0
    result = session.execute(
        update(Cue)
        .where(Cue.approved.is_(False), Cue.source == "ANALYSIS")
        .values(approved=True, approved_by="AUTO")
    )
    return result.rowcount or 0


def _copies(session: Session, track: Track) -> list[Track]:
    return list(session.scalars(select(Track).where(Track.file_hash == track.file_hash)))


def approve(session: Session, track: Track) -> int:
    """The DJ validated the cues of this file (every identical copy)."""
    count = 0
    for copy in _copies(session, track):
        for cue in cues_of(session, copy.id):
            count += not cue.approved
            cue.approved, cue.approved_by = True, "USER"
    return count


def remove(session: Session, track: Track, cue_id: uuid.UUID) -> bool:
    cue = session.get(Cue, cue_id)
    if cue is None or cue.track_id != track.id:
        return False
    session.execute(
        delete(Cue).where(Cue.slot == cue.slot, Cue.track_id.in_([c.id for c in _copies(session, track)]))
    )
    return True
