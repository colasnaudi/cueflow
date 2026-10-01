"""Audio analysis (BPM, beatgrid, downbeat, key, energy): one track on demand or the whole library.

Results land in `beatgrids` and `audio_analysis`. The catalogue's BPM/key are only filled when empty;
replacing a tagged value is an explicit user action (`apply`). A user-corrected beatgrid is never overwritten.
"""

import logging
import multiprocessing
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.audio import rhythm
from app.config import get_settings
from app.db import SessionLocal
from app.models import AudioAnalysis, Beatgrid, Cue, Section, Track
from app.services import cues
from app.services.cue_engine import plan_cues
from app.services.folders import is_sample_folder
from app.services.jobs import JobStatus
from app.services.queries import folder_filter

log = logging.getLogger(__name__)

MIN_DURATION_MS = 60_000
WORKER_RECYCLE_TASKS = 50

status = JobStatus()
_lock = threading.Lock()


def copies_of(session: Session, track: Track) -> list[Track]:
    """Identical files share one analysis."""
    return list(session.scalars(select(Track).where(Track.file_hash == track.file_hash)))


def dsp_analysis(session: Session, track_id) -> AudioAnalysis | None:
    return session.scalar(
        select(AudioAnalysis).where(
            AudioAnalysis.track_id == track_id, AudioAnalysis.analyzer_version == rhythm.ANALYZER_VERSION
        )
    )


def save(session: Session, track: Track, result: dict, reset_grid: bool = False) -> None:
    for copy in copies_of(session, track):
        grid = session.get(Beatgrid, copy.id)
        if grid is None:
            grid = Beatgrid(track_id=copy.id)
            session.add(grid)
        if grid.source != "USER" or reset_grid:
            grid.bpm, grid.first_beat = result["bpm"], result["first_beat"]
            grid.downbeat_offset, grid.beats_per_bar = result["downbeat_offset"], rhythm.BEATS_PER_BAR
            grid.grid_confidence, grid.downbeat_confidence = (
                result["grid_confidence"],
                result["downbeat_confidence"],
            )
            grid.source, grid.analyzer_version = "ANALYSIS", rhythm.ANALYZER_VERSION

        analysis = dsp_analysis(session, copy.id)
        if analysis is None:
            analysis = AudioAnalysis(track_id=copy.id, analyzer_version=rhythm.ANALYZER_VERSION)
            session.add(analysis)
        analysis.musical_key, analysis.camelot_key = result["musical_key"], result["camelot_key"]
        analysis.key_strength, analysis.energy_curve = result["key_strength"], result["energy_curve"]
        analysis.vocal_curve = result["vocal_curve"]
        analysis.vocal_probability = result["vocal_probability"]
        analysis.instrumental_probability = round(1 - result["vocal_probability"], 3)
        analysis.analyzed_at = datetime.now()

        # Detected sections are replaced; sections typed by the user (future cue editor) are kept.
        session.execute(delete(Section).where(Section.track_id == copy.id, Section.source == "AUDIO"))
        for section in result["sections"]:
            session.add(Section(track_id=copy.id, analyzer_version=rhythm.ANALYZER_VERSION, **section))
        detected = [
            SimpleNamespace(**{"start_beat": 0, "end_beat": 0, **section}) for section in result["sections"]
        ]
        cues.replace_suggestions(session, copy.id, plan_cues(detected, result["vocal_curve"]))

        # Fill the catalogue only where the file had nothing.
        if copy.bpm is None:
            copy.bpm, copy.bpm_source = round(result["bpm"], 2), "ANALYSIS"
        if copy.camelot_key is None and result["camelot_key"]:
            copy.musical_key, copy.camelot_key, copy.key_source = (
                result["musical_key"],
                result["camelot_key"],
                "ANALYSIS",
            )
        if copy.status == "NOT_ANALYZED":
            copy.status = "ANALYZED"


def analyse_track(session: Session, track: Track, reset_grid: bool = False) -> None:
    save(session, track, rhythm.analyse(track.path).as_dict(), reset_grid=reset_grid)
    session.commit()


def apply(session: Session, track: Track, fields: set[str]) -> None:
    """Explicit user choice: replace the catalogue BPM and/or key by the analysed ones (every copy)."""
    grid, analysis = session.get(Beatgrid, track.id), dsp_analysis(session, track.id)
    for copy in copies_of(session, track):
        if "bpm" in fields and grid is not None:
            copy.bpm, copy.bpm_source = round(float(grid.bpm), 2), "ANALYSIS"
        if "key" in fields and analysis is not None and analysis.camelot_key:
            copy.musical_key, copy.camelot_key, copy.key_source = (
                analysis.musical_key,
                analysis.camelot_key,
                "ANALYSIS",
            )


def shift_downbeat(session: Session, track: Track, beats: int) -> None:
    """User correction: move bar 1 by whole beats. The grid becomes USER and survives re-analysis."""
    for copy in copies_of(session, track):
        grid = session.get(Beatgrid, copy.id)
        if grid is not None:
            grid.downbeat_offset = (grid.downbeat_offset + beats) % grid.beats_per_bar
            grid.source = "USER"


def eligible_tracks(session: Session, folder: str | None = None, force: bool = False) -> list[Track]:
    """Real tracks (not samples), one copy per file, tracks without BPM/key first. Only unanalysed ones unless
    `force` (re-analyse everything; grids and cues the DJ locked are kept by `save`)."""
    query = select(Track).where(Track.duration_ms >= MIN_DURATION_MS)
    if not force:
        analysed = select(AudioAnalysis.track_id).where(
            AudioAnalysis.analyzer_version == rhythm.ANALYZER_VERSION
        )
        query = query.where(Track.id.not_in(analysed))
    if folder:
        query = query.where(folder_filter(folder))
    tracks = session.scalars(
        query.order_by(or_(Track.bpm.is_(None), Track.camelot_key.is_(None)).desc(), Track.path)
    ).all()
    seen: set[str] = set()
    result = []
    for track in tracks:
        if track.file_hash not in seen and not is_sample_folder(track.path):
            seen.add(track.file_hash)
            result.append(track)
    return result


def _analyse_file(path: str) -> dict:
    """Runs in a worker process: pure DSP, no database access."""
    return rhythm.analyse(path).as_dict()


def run(
    limit: int | None = None, workers: int | None = None, folder: str | None = None, force: bool = False
) -> JobStatus:
    global status
    with _lock:
        if status.running:
            raise RuntimeError("Audio analysis is already running")
        status = JobStatus(state="running", running=True, phase="audio", scope=folder, started_at=time.time())

    try:
        with SessionLocal() as session:
            # Tracks analysed before cues existed get them from their stored sections (no audio needed).
            status.phase = "cues"
            for track in tracks_without_cues(session):
                regenerate_cues(session, track)
            cues.auto_approve_pending(session)
            session.commit()

            status.phase = "audio"
            tracks = eligible_tracks(session, folder, force)[:limit]
            status.total = len(tracks)
            by_path = {t.path: t for t in tracks}
            # Workers are recycled every 50 tracks so a library-wide run keeps a flat memory footprint.
            with ProcessPoolExecutor(
                max_workers=workers or get_settings().analysis_workers,
                max_tasks_per_child=WORKER_RECYCLE_TASKS,
                mp_context=multiprocessing.get_context("spawn"),
            ) as pool:
                futures = {pool.submit(_analyse_file, t.path): t.path for t in tracks}
                for future in as_completed(futures):
                    track = by_path[futures[future]]
                    status.current = f"{track.artist or ''} – {track.title or track.filename}".strip(" –")
                    try:
                        save(session, track, future.result())
                        session.commit()
                        status.analyzed += 1
                    except Exception as exc:  # one unreadable file must not stop the library run
                        session.rollback()
                        log.warning("audio analysis failed for %s: %s", track.path, exc)
                        status.errors.append(f"{track.path}: {exc}")
                    status.processed += 1
                    if status.stop_requested:
                        pool.shutdown(wait=True, cancel_futures=True)
                        break
            refresh_live_xml(session)
        status.state = "stopped" if status.stop_requested else "completed"
    except Exception as exc:
        status.state, status.error = "failed", str(exc)
        raise
    finally:
        status.running = False
        status.current = None
        status.finished_at = time.time()
    return status


def start_in_background(limit: int | None = None, folder: str | None = None, force: bool = False) -> None:
    if status.running:
        raise RuntimeError("Audio analysis is already running")

    def job() -> None:
        try:
            run(limit, folder=folder, force=force)
        except Exception:  # recorded in status (state=failed); keep the traceback in the logs
            log.exception("audio analysis failed")

    threading.Thread(target=job, daemon=True).start()


def request_stop() -> None:
    status.stop_requested = True


def sections_of(session: Session, track_id) -> list[Section]:
    return list(
        session.scalars(select(Section).where(Section.track_id == track_id).order_by(Section.start_bar))
    )


def regenerate_cues(session: Session, track: Track) -> None:
    """Re-plan the suggested cues from the stored sections (approved and user cues are kept)."""
    dsp = dsp_analysis(session, track.id)
    planned = plan_cues(sections_of(session, track.id), (dsp.vocal_curve or []) if dsp else [])
    for copy in copies_of(session, track):
        cues.replace_suggestions(session, copy.id, planned)


def tracks_without_cues(session: Session) -> list[Track]:
    has_cues = select(Cue.track_id)
    analysed = select(AudioAnalysis.track_id).where(AudioAnalysis.analyzer_version == rhythm.ANALYZER_VERSION)
    return list(session.scalars(select(Track).where(Track.id.in_(analysed), Track.id.not_in(has_cues))))


def refresh_live_xml(session: Session) -> None:
    """Rekordbox reads the live XML from a fixed path: keep it current after every analysis."""
    from app.services import rekordbox

    try:
        rekordbox.write_live(session)
    except OSError as exc:  # the analysis itself succeeded; report, do not fail the job
        log.warning("could not update the live Rekordbox XML: %s", exc)
        status.errors.append(f"Rekordbox XML not updated: {exc}")


def refresh_live_xml_now() -> None:
    """Rewrite the live Rekordbox XML in its own session (after a single-track analysis)."""
    from app.services import rekordbox

    try:
        with SessionLocal() as session:
            rekordbox.write_live(session)
    except OSError as exc:
        log.warning("could not update the live Rekordbox XML: %s", exc)
