"""Genre suggestions (folder + audio model) and the background job that produces them."""

import logging
import threading
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audio.styles import ANALYZER_VERSION, classifier
from app.config import music_root
from app.db import SessionLocal
from app.models import AudioAnalysis, GenreReview, GenreSuggestion, Track
from app.services.folders import folder_genre, is_sample_folder

log = logging.getLogger(__name__)

MIN_DURATION_MS = 60_000
FOLDER_CONFIDENCE = 0.9
MAX_AUDIO_SUGGESTIONS = 3
MIN_AUDIO_SCORE = 0.08


def build_suggestions(
    folder: str | None, styles: list[dict] | None, vocabulary: dict[str, str]
) -> list[dict]:
    """Ranked, de-duplicated suggestions. `vocabulary` maps lower-case genre -> the spelling already used."""
    suggestions: list[dict] = []
    seen: set[str] = set()

    def add(genre: str, confidence: float, source: str) -> None:
        key = genre.lower()
        if key in seen:
            # Folder and audio agree: keep the folder entry but raise its confidence.
            for s in suggestions:
                if s["genre"].lower() == key:
                    s["confidence"] = min(0.99, max(s["confidence"], confidence) + 0.05)
                    s["source"] = "FOLDER+AUDIO"
            return
        seen.add(key)
        suggestions.append(
            {"genre": vocabulary.get(key, genre), "confidence": round(confidence, 3), "source": source}
        )

    if folder:
        add(folder, FOLDER_CONFIDENCE, "FOLDER")
    audio = [s for s in styles or [] if s["score"] >= MIN_AUDIO_SCORE][:MAX_AUDIO_SUGGESTIONS]
    for style in audio:
        add(style["style"], style["score"], "AUDIO")
    for rank, suggestion in enumerate(suggestions):
        suggestion["rank"] = rank
    return suggestions


def genre_vocabulary(session: Session) -> dict[str, str]:
    genres = session.scalars(select(Track.genre).where(Track.genre.is_not(None)).distinct()).all()
    return {g.lower(): g for g in genres}


def save_suggestions(session: Session, track: Track, suggestions: list[dict]) -> None:
    session.execute(delete(GenreSuggestion).where(GenreSuggestion.track_id == track.id))
    for s in suggestions:
        session.add(GenreSuggestion(track_id=track.id, **s))
    if suggestions:
        # Reviewed tracks keep their decision; only new tracks enter the queue.
        session.execute(insert(GenreReview).values(track_id=track.id).on_conflict_do_nothing())


@dataclass
class JobStatus:
    state: str = "idle"  # idle | running | completed | stopped | failed
    running: bool = False
    error: str | None = None
    phase: str | None = None
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    reused: int = 0
    current: str | None = None
    errors: list[str] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None
    stop_requested: bool = False

    def as_dict(self) -> dict:
        data = asdict(self) | {"error_count": len(self.errors), "errors": self.errors[-20:]}
        data.pop("stop_requested")
        return data


status = JobStatus()
_lock = threading.Lock()


def eligible_tracks(session: Session) -> list[Track]:
    """Real tracks (not samples), one copy per file, tracks without a genre first."""
    tracks = session.scalars(
        select(Track)
        .where(or_(Track.duration_ms >= MIN_DURATION_MS, Track.duration_ms.is_(None)))
        .order_by(Track.genre.is_not(None), Track.created_at, Track.path)
    ).all()
    seen: set[str] = set()
    result = []
    for track in tracks:
        if track.file_hash in seen or is_sample_folder(track.path):
            continue
        seen.add(track.file_hash)
        result.append(track)
    return result


def run(limit: int | None = None) -> JobStatus:
    """Phase 1: folder suggestions for every track (instant). Phase 2: audio model, track by track."""
    global status
    with _lock:
        if status.running:
            raise RuntimeError("Genre analysis is already running")
        status = JobStatus(state="running", running=True, phase="folders", started_at=time.time())

    try:
        root = music_root()
        with SessionLocal() as session:
            vocabulary = genre_vocabulary(session)
            tracks = eligible_tracks(session)
            analyses = {
                a.track_id: a.styles
                for a in session.scalars(
                    select(AudioAnalysis).where(AudioAnalysis.analyzer_version == ANALYZER_VERSION)
                )
            }
            for track in tracks:
                save_suggestions(
                    session,
                    track,
                    build_suggestions(folder_genre(track.path, root), analyses.get(track.id), vocabulary),
                )
            session.commit()

            todo = [t for t in tracks if t.id not in analyses][:limit]
            status.phase, status.total = "audio", len(todo)
            for track in todo:
                if status.stop_requested:
                    break
                status.current = f"{track.artist or ''} – {track.title or track.filename}".strip(" –")
                try:
                    styles = classifier.classify(track.path)
                    session.add(
                        AudioAnalysis(track_id=track.id, styles=styles, analyzer_version=ANALYZER_VERSION)
                    )
                    save_suggestions(
                        session, track, build_suggestions(folder_genre(track.path, root), styles, vocabulary)
                    )
                    session.commit()
                    status.analyzed += 1
                except Exception as exc:  # a corrupt file must not stop the queue
                    session.rollback()
                    log.warning("genre analysis failed for %s: %s", track.path, exc)
                    status.errors.append(f"{track.path}: {exc}")
                status.processed += 1
        status.state = "stopped" if status.stop_requested else "completed"
    except Exception as exc:
        status.state, status.error = "failed", str(exc)
        raise
    finally:
        status.running = False
        status.current = None
        status.finished_at = time.time()
    return status


def start_in_background(limit: int | None = None) -> None:
    if status.running:
        raise RuntimeError("Genre analysis is already running")

    def job() -> None:
        try:
            run(limit)
        except Exception:  # recorded in status (state=failed); keep the traceback in the logs
            log.exception("genre analysis failed")

    threading.Thread(target=job, daemon=True).start()


def request_stop() -> None:
    status.stop_requested = True
