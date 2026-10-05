"""Audio editor: a working edit is an edit list over the original, rendered only when exported.

The original file is only ever read. The browser previews the same edit list over the same decode (served by
`source_wav`), so what the DJ hears is what gets exported.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import edits_dir, get_settings
from app.models import Track, TrackEdit
from app.schemas import EditExport, EditList, EditSegment
from app.services import edit_catalogue
from app.services.media import _ffmpeg, _source

CHANNELS = 2
DEFAULT_SAMPLE_RATE = 44_100
# Decoded originals kept for the editor preview (~60 MB per 6-minute track).
SOURCE_CACHE_SIZE = 5
CODECS = {("wav", 16): ["-c:a", "pcm_s16le"], ("wav", 24): ["-c:a", "pcm_s24le"]}


def sample_rate(track: Track) -> int:
    return track.sample_rate or DEFAULT_SAMPLE_RATE


def saved(session: Session, track: Track) -> TrackEdit | None:
    return session.scalar(select(TrackEdit).where(TrackEdit.track_id == track.id))


def _check_rate(track: Track, edit: EditList) -> None:
    if edit.sample_rate != sample_rate(track):
        raise HTTPException(
            422, f"Edit is at {edit.sample_rate} Hz, the track decodes at {sample_rate(track)} Hz"
        )


def save(session: Session, track: Track, edit: EditList) -> TrackEdit:
    _check_rate(track, edit)
    row = saved(session, track) or TrackEdit(track_id=track.id)
    row.edit = edit.model_dump(mode="json")
    row.updated_at = datetime.now()
    session.add(row)
    session.flush()
    return row


def reset(session: Session, track: Track) -> None:
    if row := saved(session, track):
        session.delete(row)


def _decode_args(track: Track) -> list[str]:
    return ["-i", str(_source(track)), "-map", "0:a:0", "-ac", str(CHANNELS), "-ar", str(sample_rate(track))]


def decode(track: Track) -> np.ndarray:
    """The original as float32 frames (n, 2) at the editor's sample rate."""
    raw = _ffmpeg(*_decode_args(track), "-f", "f32le", "-")
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, CHANNELS)


def source_wav(track: Track) -> Path:
    """The same decode as `decode`, as a 16-bit WAV for the browser (cached, a few tracks at a time)."""
    folder = get_settings().data_dir / "cache" / "editor"
    cached = folder / f"{track.file_hash}.{sample_rate(track)}.wav"
    if not cached.exists():
        folder.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".tmp.wav")
        _ffmpeg("-y", *_decode_args(track), "-c:a", "pcm_s16le", str(tmp))
        tmp.rename(cached)
        # Cache files only (never audio from the library): drop the least recently used decodes.
        for old in sorted(folder.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)[
            SOURCE_CACHE_SIZE:
        ]:
            old.unlink(missing_ok=True)
    else:
        cached.touch()
    return cached


def _envelope(segment: EditSegment, length: int) -> np.ndarray | None:
    if not segment.ramps:
        return None
    envelope = np.ones(length, dtype=np.float32)
    position = np.arange(length, dtype=np.float32) / length
    for g0, g1 in segment.ramps:
        envelope *= g0 + (g1 - g0) * position
    return envelope


def render(audio: np.ndarray, edit: EditList) -> np.ndarray:
    """Concatenate the segments (with their ramps), then apply the global gain.

    Mirrors `renderEdit` in apps/web/lib/editor.ts.
    """
    parts = []
    for segment in edit.segments:
        if segment.end > len(audio):
            raise HTTPException(
                422, f"Segment ends at frame {segment.end}, the track has {len(audio)} frames"
            )
        part = audio[segment.start : segment.end]
        envelope = _envelope(segment, len(part))
        parts.append(part * envelope[:, None] if envelope is not None else part)
    return np.concatenate(parts) * np.float32(10 ** (edit.gain_db / 20))


def _reserve(stem: str, extension: str) -> Path:
    """Create an empty `<stem> (Edited).<ext>` that did not exist yet: never overwrites an existing file."""
    folder = edits_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stem = stem.replace(os.sep, "_")
    for n in range(1, 1000):
        path = folder / f"{stem} (Edited{'' if n == 1 else f' {n}'}).{extension}"
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            continue
    raise HTTPException(409, f"Too many edits of {stem} in {folder}")


def export(session: Session, track: Track, body: EditExport) -> tuple[Path, int, Track]:
    """Render the edit into a new file in EDITS_DIR (tags copied from the original, title marked as an
    edit) and add it to the catalogue with the DJ's preparation carried over.

    Returns (path, frames, new catalogue track).
    """
    _check_rate(track, body.edit)
    rate = body.edit.sample_rate
    audio = np.clip(render(decode(track), body.edit), -1, 1).astype(np.float32)
    target = _reserve(Path(track.filename).stem, body.format)
    tmp = target.with_name(f".{target.name}.tmp")
    codec = CODECS.get((body.format, body.quality)) or [
        "-c:a", "libmp3lame", "-b:a", f"{body.quality}k", "-id3v2_version", "3",
    ]  # fmt: skip
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-y",
        "-f", "f32le", "-ar", str(rate), "-ac", str(CHANNELS), "-i", "pipe:0",
        "-i", str(_source(track)),
        "-map", "0:a", "-map_metadata", "1", "-metadata", f"title={_edited_title(track, target)}",
        *codec, "-f", body.format, str(tmp),
    ]  # fmt: skip
    try:
        subprocess.run(command, input=audio.tobytes(), capture_output=True, check=True, timeout=600)
        os.replace(tmp, target)  # only ever replaces the empty placeholder reserved above
    except subprocess.CalledProcessError as exc:
        tmp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)  # our own empty placeholder, not a library file
        raise HTTPException(500, f"ffmpeg failed: {exc.stderr.decode(errors='replace')[:300]}") from exc
    return target, len(audio), edit_catalogue.register(session, track, target, body.edit)


def _edited_title(track: Track, target: Path) -> str:
    """ "Title (Edited 2)": the original title plus the suffix of the file name chosen by `_reserve`."""
    suffix = target.stem[len(Path(track.filename).stem.replace(os.sep, "_")) :].strip()
    return f"{track.title or Path(track.filename).stem} {suffix}"
