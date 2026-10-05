import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.routes.tracks import get_track
from app.schemas import CueCreate, CueOut, CueUpdate, ExportPreview, LiveXml, RekordboxExport
from app.services import analysis, cues, rekordbox

router = APIRouter(tags=["cues"])


@router.get("/tracks/{track_id}/cues", response_model=list[CueOut])
def list_cues(track_id: uuid.UUID, session: Session = Depends(get_session)):
    get_track(session, track_id)
    return cues.cues_of(session, track_id)


@router.post("/tracks/{track_id}/cues/approve", response_model=list[CueOut])
def approve_cues(track_id: uuid.UUID, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    cues.approve(session, track)
    session.commit()
    return cues.cues_of(session, track_id)


@router.post("/tracks/{track_id}/cues/regenerate", response_model=list[CueOut])
def regenerate_cues(track_id: uuid.UUID, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    if analysis.dsp_analysis(session, track_id) is None:
        raise HTTPException(409, "Analyse the track before generating cues")
    analysis.regenerate_cues(session, track)
    session.commit()
    return cues.cues_of(session, track_id)


@router.post("/tracks/{track_id}/cues", response_model=list[CueOut], status_code=201)
def create_cue(
    track_id: uuid.UUID, body: CueCreate, background: BackgroundTasks, session: Session = Depends(get_session)
):
    """A hot cue, memory cue or loop placed by the DJ at a musical position."""
    track = get_track(session, track_id)
    try:
        cues.create(session, track, body.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    background.add_task(analysis.refresh_live_xml_now)
    return cues.cues_of(session, track_id)


@router.patch("/tracks/{track_id}/cues/{cue_id}", response_model=list[CueOut])
def edit_cue(
    track_id: uuid.UUID,
    cue_id: uuid.UUID,
    body: CueUpdate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
):
    track = get_track(session, track_id)
    try:
        cue = cues.edit(session, track, cue_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if cue is None:
        raise HTTPException(404, "Cue not found")
    session.commit()
    background.add_task(analysis.refresh_live_xml_now)
    return cues.cues_of(session, track_id)


@router.delete("/tracks/{track_id}/cues/{cue_id}", response_model=list[CueOut])
def delete_cue(track_id: uuid.UUID, cue_id: uuid.UUID, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    if not cues.remove(session, track, cue_id):
        raise HTTPException(404, "Cue not found")
    session.commit()
    return cues.cues_of(session, track_id)


@router.get("/export/rekordbox/preview", response_model=ExportPreview)
def export_preview(
    folder: str | None = None,
    approved_only: bool = Query(default=True),
    session: Session = Depends(get_session),
):
    items = rekordbox.collect(session, folder, approved_only)
    every = rekordbox.collect(session, folder, approved_only=False)
    return ExportPreview(
        tracks=len(items),
        hot_cues=sum(c.type == "HOT" for item in items for c in item.cues),
        memory_cues=sum(c.type == "MEMORY" for item in items for c in item.cues),
        unapproved_tracks=sum(1 for item in every if item.cues and not all(c.approved for c in item.cues)),
    )


@router.post("/export/rekordbox")
def export_rekordbox(body: RekordboxExport, session: Session = Depends(get_session)):
    """Build a rekordbox.xml (also kept in data/exports/). Nothing is written to Rekordbox itself."""
    items = rekordbox.collect(session, body.folder, body.approved_only)
    if not items:
        raise HTTPException(422, "No analysed track with cues to export")
    stamp = datetime.now()
    name = f"Cueflow {stamp:%Y-%m-%d %H:%M}" + (f" · {body.folder.rsplit('/', 1)[-1]}" if body.folder else "")
    xml = rekordbox.build(items, body.include_beatgrid, get_settings().rekordbox_mp3_offset_ms, name)
    exports = get_settings().data_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    filename = f"cueflow-rekordbox-{stamp:%Y%m%d-%H%M%S}.xml"
    (exports / filename).write_bytes(xml)
    return Response(
        xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/rekordbox/live", response_model=LiveXml)
def live_xml():
    return rekordbox.live_status()


@router.post("/export/rekordbox/live", response_model=LiveXml)
def refresh_live_xml(session: Session = Depends(get_session)):
    """Rewrite the XML Rekordbox reads (it is also rewritten after every audio analysis)."""
    return rekordbox.write_live(session)
