import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Beatgrid
from app.routes.tracks import get_track
from app.schemas import ApplyAnalysis, ShiftDownbeat, TrackAnalysis, TrackOut
from app.services import analysis

router = APIRouter(tags=["analysis"])


def analysis_view(session: Session, track_id: uuid.UUID) -> TrackAnalysis:
    dsp = analysis.dsp_analysis(session, track_id)
    return TrackAnalysis(
        beatgrid=session.get(Beatgrid, track_id),
        musical_key=dsp.musical_key if dsp else None,
        camelot_key=dsp.camelot_key if dsp else None,
        key_strength=dsp.key_strength if dsp else None,
        energy_curve=dsp.energy_curve or [] if dsp else [],
        sections=analysis.sections_of(session, track_id),
        vocal_curve=dsp.vocal_curve or [] if dsp else [],
        vocal_probability=dsp.vocal_probability if dsp else None,
        analyzed_at=dsp.analyzed_at if dsp else None,
    )


@router.get("/tracks/{track_id}/analysis", response_model=TrackAnalysis)
def read_analysis(track_id: uuid.UUID, session: Session = Depends(get_session)):
    get_track(session, track_id)
    return analysis_view(session, track_id)


@router.post("/tracks/{track_id}/analysis", response_model=TrackAnalysis)
def analyse_now(
    track_id: uuid.UUID,
    reset_grid: bool = Query(default=False, description="Also replace a beatgrid corrected by the user"),
    session: Session = Depends(get_session),
):
    """Analyse one track synchronously (a few seconds)."""
    track = get_track(session, track_id)
    try:
        analysis.analyse_track(session, track, reset_grid=reset_grid)
    except (RuntimeError, ValueError) as exc:  # Essentia cannot decode the file / no rhythm found
        raise HTTPException(422, f"Analysis failed: {exc}") from exc
    return analysis_view(session, track_id)


@router.post("/tracks/{track_id}/analysis/apply", response_model=TrackOut)
def apply_analysis(track_id: uuid.UUID, body: ApplyAnalysis, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    analysis.apply(session, track, set(body.fields))
    session.commit()
    session.refresh(track)
    return track


@router.post("/tracks/{track_id}/beatgrid/shift", response_model=TrackAnalysis)
def shift_downbeat(track_id: uuid.UUID, body: ShiftDownbeat, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    if session.get(Beatgrid, track_id) is None:
        raise HTTPException(409, "Analyse the track before adjusting its beatgrid")
    analysis.shift_downbeat(session, track, body.beats)
    session.commit()
    return analysis_view(session, track_id)


@router.get("/analysis/audio")
def audio_status():
    return analysis.status.as_dict()


@router.post("/analysis/audio", status_code=202)
def start_audio_analysis(
    limit: int | None = Query(default=None, ge=1),
    folder: str | None = Query(
        default=None, description="Folder relative to MUSIC_ROOT, subfolders included"
    ),
    force: bool = Query(default=False, description="Re-analyse tracks that were already analysed"),
):
    try:
        analysis.start_in_background(limit, folder=folder, force=force)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"started": True}


@router.post("/analysis/audio/stop")
def stop_audio_analysis():
    analysis.request_stop()
    return analysis.status.as_dict()
