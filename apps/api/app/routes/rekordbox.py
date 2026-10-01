import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import RekordboxTrack
from app.routes.tracks import get_track
from app.services import rekordbox_import

router = APIRouter(prefix="/rekordbox", tags=["rekordbox"])

MAX_IMPORT_BYTES = 200 * 1024 * 1024


@router.post("/import")
async def import_collection(request: Request, session: Session = Depends(get_session)):
    """Body: the XML of Rekordbox's File > Export Collection in xml format (sent as is, no file path)."""
    body = await request.body()
    if not body or len(body) > MAX_IMPORT_BYTES:
        raise HTTPException(422, "Send the Rekordbox collection XML as the request body")
    try:
        return rekordbox_import.import_collection(session, io.BytesIO(body))
    except Exception as exc:  # malformed XML: tell the user, keep the database untouched
        session.rollback()
        raise HTTPException(422, f"Not a Rekordbox collection XML: {exc}") from exc


@router.get("/import")
def import_status(session: Session = Depends(get_session)):
    rows = select(RekordboxTrack)
    return {
        "imported_at": session.scalar(select(func.max(RekordboxTrack.imported_at))),
        "entries": session.scalar(select(func.count()).select_from(rows.subquery())),
        "matched": session.scalar(select(func.count()).where(RekordboxTrack.track_id.is_not(None))),
        "rated": session.scalar(select(func.count()).where(RekordboxTrack.rating > 0)),
    }


@router.get("/grids")
def grids(session: Session = Depends(get_session)):
    """Cueflow vs Rekordbox beatgrids per format (BPM agreement, phase offset, bar 1 agreement)."""
    return rekordbox_import.grid_comparison(session)


@router.get("/tracks/{track_id}")
def track_snapshot(track_id: uuid.UUID, session: Session = Depends(get_session)):
    get_track(session, track_id)
    row = session.scalar(select(RekordboxTrack).where(RekordboxTrack.track_id == track_id))
    if row is None:
        return None
    marks = row.position_marks or []
    return {
        "rating": row.rating,
        "bpm": float(row.bpm) if row.bpm else None,
        "tonality": row.tonality,
        "comments": row.comments,
        "play_count": row.play_count,
        "hot_cues": sum(m.get("num") not in (None, "-1") for m in marks),
        "memory_cues": sum(m.get("num") == "-1" for m in marks),
        "imported_at": row.imported_at,
    }
