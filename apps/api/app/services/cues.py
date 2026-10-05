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


HOT_SLOTS = "ABCDEFGH"


def _free_slot(session: Session, track_id: uuid.UUID, type: str) -> str:
    used = {c.slot for c in session.scalars(select(Cue).where(Cue.track_id == track_id))}
    if type == "HOT":
        slot = next((s for s in HOT_SLOTS if s not in used), None)
        if slot is None:
            raise ValueError("All 8 hot cues (A-H) are used: delete one or add a memory cue")
        return slot
    # U##, not M##: generated memory cues (M01...) never collide with the DJ's.
    return next(f"U{n:02d}" for n in range(1, 1000) if f"U{n:02d}" not in used)


def create(session: Session, track: Track, fields: dict) -> Cue:
    """A cue (or loop, with `loop_beats`) placed by the DJ, on every identical copy. Never replaced."""
    slot = fields.pop("slot", None) or _free_slot(session, track.id, fields["type"])
    created = None
    for copy in _copies(session, track):
        if session.scalar(select(Cue).where(Cue.track_id == copy.id, Cue.slot == slot)):
            raise ValueError(f"Hot cue {slot} is already used")
        cue = Cue(track_id=copy.id, slot=slot, source="USER", approved=True, approved_by="USER", **fields)
        session.add(cue)
        if copy.id == track.id:
            created = cue
    session.flush()
    return created


def edit(session: Session, track: Track, cue_id: uuid.UUID, changes: dict) -> Cue | None:
    """Move, rename, recolour, resize or re-slot a cue (every copy). It becomes the DJ's: never replaced."""
    cue = session.get(Cue, cue_id)
    if cue is None or cue.track_id != track.id:
        return None
    # bar, beat and slot cannot be cleared; label, colour and loop length can (None).
    changes = {k: v for k, v in changes.items() if v is not None or k in ("label", "color", "loop_beats")}
    new_slot = changes.pop("slot", None)
    if (
        new_slot
        and new_slot != cue.slot
        and session.scalar(select(Cue).where(Cue.track_id == track.id, Cue.slot == new_slot))
    ):
        raise ValueError(f"Hot cue {new_slot} is already used")
    for copy in _copies(session, track):
        same = session.scalar(select(Cue).where(Cue.track_id == copy.id, Cue.slot == cue.slot))
        if same is None:
            continue
        for field, value in changes.items():
            setattr(same, field, value)
        if new_slot:
            same.slot = new_slot
        same.approved, same.approved_by = True, "USER"
    session.flush()
    return cue
