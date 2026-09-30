"""Serve audio to the browser and compute waveform peaks (cached under data/)."""

import json
import subprocess
from pathlib import Path

import numpy as np
from fastapi import HTTPException

from app.config import get_settings
from app.models import Track

MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}
# Browsers cannot decode AIFF: transcode once to FLAC (lossless) and cache it.
TRANSCODE = {".aif", ".aiff"}

PEAK_SAMPLE_RATE = 8000
PEAKS_PER_SECOND = 50
# Bump when the peak algorithm changes, so cached waveforms are recomputed.
PEAKS_VERSION = 2


def _source(track: Track) -> Path:
    path = Path(track.path)
    if not path.exists():
        raise HTTPException(404, f"File missing on disk: {path}")
    return path


def _ffmpeg(*args: str) -> bytes:
    try:
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-nostdin", *args], capture_output=True, check=True, timeout=300
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise HTTPException(500, f"ffmpeg failed: {exc.stderr.decode(errors='replace')[:300]}") from exc


def playable_file(track: Track) -> tuple[Path, str]:
    path = _source(track)
    suffix = path.suffix.lower()
    if suffix not in TRANSCODE:
        return path, MEDIA_TYPES.get(suffix, "application/octet-stream")

    cached = get_settings().data_dir / "cache" / f"{track.file_hash}.flac"
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".tmp.flac")
        _ffmpeg("-y", "-i", str(path), "-map", "0:a:0", str(tmp))
        tmp.rename(cached)
    return cached, "audio/flac"


def peaks(track: Track) -> dict:
    """RMS loudness per bucket, normalised to [0, 1], as WaveSurfer `peaks`.

    RMS rather than max-abs: mastered house tracks peak at 0 dBFS almost everywhere, so max-abs renders a flat
    block while RMS keeps breaks and drops visible.
    """
    cached = get_settings().data_dir / "waveforms" / f"{track.file_hash}.v{PEAKS_VERSION}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    raw = _ffmpeg(
        "-i",
        str(_source(track)),
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(PEAK_SAMPLE_RATE),
        "-f",
        "s16le",
        "-",
    )
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    duration = len(samples) / PEAK_SAMPLE_RATE
    bucket = PEAK_SAMPLE_RATE // PEAKS_PER_SECOND
    usable = len(samples) // bucket * bucket
    values = (
        np.sqrt(np.mean(np.square(samples[:usable].reshape(-1, bucket)), axis=1)) if usable else np.zeros(1)
    )
    top = float(values.max()) or 1.0
    result = {"duration": round(duration, 3), "peaks": np.round(values / top, 3).tolist()}

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(result, separators=(",", ":")))
    return result
