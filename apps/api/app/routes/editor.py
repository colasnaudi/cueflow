import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Track, TrackEdit
from app.routes.tracks import get_track
from app.schemas import EditExport, EditExportResult, EditList, TrackEditOut
from app.services import editor

router = APIRouter(prefix="/tracks/{track_id}/edit", tags=["editor"])


def _out(track: Track, row: TrackEdit | None) -> TrackEditOut:
    return TrackEditOut(
        track_id=track.id,
        sample_rate=editor.sample_rate(track),
        edit=EditList.model_validate(row.edit) if row else None,
        updated_at=row.updated_at if row else None,
    )


@router.get("", response_model=TrackEditOut)
def read_edit(track_id: uuid.UUID, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    return _out(track, editor.saved(session, track))


@router.put("", response_model=TrackEditOut)
def save_edit(track_id: uuid.UUID, body: EditList, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    row = editor.save(session, track, body)
    session.commit()
    return _out(track, row)


@router.delete("", response_model=TrackEditOut)
def reset_edit(track_id: uuid.UUID, session: Session = Depends(get_session)):
    """Reset to the original: forgets the saved working edit. The audio file was never touched."""
    track = get_track(session, track_id)
    editor.reset(session, track)
    session.commit()
    return _out(track, None)


@router.get("/source")
def edit_source(track_id: uuid.UUID, session: Session = Depends(get_session)):
    """The decoded original the editor works on (same decoder as the export)."""
    return FileResponse(editor.source_wav(get_track(session, track_id)), media_type="audio/wav")


@router.post("/export", response_model=EditExportResult)
def export_edit(track_id: uuid.UUID, body: EditExport, session: Session = Depends(get_session)):
    """Render the edit into a new file in EDITS_DIR. The original is only read, never overwritten."""
    track = get_track(session, track_id)
    path, frames, new = editor.export(session, track, body)
    session.commit()
    return EditExportResult(
        path=str(path),
        filename=path.name,
        duration_ms=round(frames * 1000 / body.edit.sample_rate),
        track_id=new.id,
    )
