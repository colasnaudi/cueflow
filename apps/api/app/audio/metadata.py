"""Read tag metadata from audio files (ID3 / MP4 / Vorbis), with a filename fallback."""

import json
import re
import struct
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import mutagen
from mutagen.id3 import ID3
from mutagen.mp4 import MP4Tags

from app.audio.keys import normalize_key

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a"}

ID3_FIELDS = {
    "title": ["TIT2"],
    "artist": ["TPE1"],
    "album": ["TALB"],
    "label": ["TPUB"],
    "genre": ["TCON"],
    "year": ["TDRC", "TYER"],
    "bpm": ["TBPM"],
    "key": ["TKEY", "TXXX:INITIALKEY", "TXXX:initialkey"],
}
MP4_FIELDS = {
    "title": ["©nam"],
    "artist": ["©ART", "aART"],
    "album": ["©alb"],
    "label": ["----:com.apple.iTunes:LABEL", "----:com.apple.iTunes:publisher"],
    "genre": ["©gen"],
    "year": ["©day"],
    "bpm": ["tmpo", "----:com.apple.iTunes:BPM"],
    "key": ["----:com.apple.iTunes:initialkey", "----:com.apple.iTunes:KEY"],
}
VORBIS_FIELDS = {
    "title": ["title"],
    "artist": ["artist"],
    "album": ["album"],
    "label": ["label", "organization", "publisher"],
    "genre": ["genre"],
    "year": ["date", "year"],
    "bpm": ["bpm", "tempo"],
    "key": ["initialkey", "key"],
}


@dataclass
class TrackMetadata:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    label: str | None = None
    genre: str | None = None
    year: int | None = None
    bpm: float | None = None
    musical_key: str | None = None
    camelot_key: str | None = None
    duration_ms: int | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    rating: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    elif hasattr(value, "text"):  # ID3 text frame
        value = ", ".join(str(v) for v in value.text)
    elif isinstance(value, list | tuple):
        value = ", ".join(_as_text(v) or "" for v in value)
    text = str(value).replace("\x00", "").strip()
    return text or None


def _first(tags, keys: list[str]) -> str | None:
    for key in keys:
        try:
            value = tags.get(key) if not isinstance(tags, ID3) else tags.getall(key) or None
        except (KeyError, ValueError):
            continue
        if isinstance(tags, ID3) and value:
            value = value[0]
        if (text := _as_text(value)) is not None:
            return text
    return None


def _parse_bpm(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        bpm = float(raw.replace(",", "."))
    except ValueError:
        return None
    return round(bpm, 2) if 40 <= bpm <= 250 else None


def _parse_year(raw: str | None) -> int | None:
    match = re.search(r"(19|20)\d{2}", raw or "")
    return int(match.group(0)) if match else None


def _popm_to_stars(tags) -> int:
    """Map a 0-255 POPM value onto 0-5 stars (Windows Media Player / Rekordbox convention)."""
    if not isinstance(tags, ID3):
        return 0
    frames = tags.getall("POPM")
    if not frames:
        return 0
    value = max(frame.rating for frame in frames)
    for stars, threshold in ((5, 224), (4, 160), (3, 96), (2, 32), (1, 1)):
        if value >= threshold:
            return stars
    return 0


def _ffprobe_duration(path: Path) -> int | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
        return int(float(json.loads(out)["format"]["duration"]) * 1000)
    except (subprocess.SubprocessError, KeyError, ValueError, OSError):
        return None


def _apply_filename_fallback(meta: TrackMetadata, path: Path) -> None:
    stem = re.sub(r"\s+", " ", path.stem).strip()
    if meta.title:
        return
    if not meta.artist and " - " in stem:
        artist, title = stem.split(" - ", 1)
        meta.artist, meta.title = artist.strip() or None, title.strip() or stem
    else:
        meta.title = stem


def read_metadata(path: Path) -> TrackMetadata:
    meta = TrackMetadata()
    try:
        audio = mutagen.File(path)
    except Exception:  # mutagen raises many format-specific errors on damaged files
        audio = None

    if audio is not None:
        info = audio.info
        if length := getattr(info, "length", None):
            meta.duration_ms = int(length * 1000)
        if bitrate := getattr(info, "bitrate", None):
            meta.bitrate = int(bitrate // 1000)
        meta.sample_rate = getattr(info, "sample_rate", None)

        tags = audio.tags
        if tags is not None:
            fields = (
                ID3_FIELDS
                if isinstance(tags, ID3)
                else MP4_FIELDS
                if isinstance(tags, MP4Tags)
                else VORBIS_FIELDS
            )
            meta.title = _first(tags, fields["title"])
            # ID3v2.3 packs several artists as "A/B"; "AC/DC"-style names are rare in DJ libraries.
            meta.artist = (artist := _first(tags, fields["artist"])) and re.sub(r"\s*/\s*", ", ", artist)
            meta.album = _first(tags, fields["album"])
            meta.label = _first(tags, fields["label"])
            meta.genre = _first(tags, fields["genre"])
            meta.year = _parse_year(_first(tags, fields["year"]))
            meta.bpm = _parse_bpm(_first(tags, fields["bpm"]))
            meta.musical_key, meta.camelot_key = normalize_key(_first(tags, fields["key"]))
            meta.rating = _popm_to_stars(tags)

    if path.suffix.lower() == ".wav":
        # WAV's native tags (RIFF INFO) are not read by mutagen; ID3 values win when both exist.
        info = read_riff_info(path)
        meta.title = meta.title or info.get("INAM")
        meta.artist = meta.artist or info.get("IART")
        meta.album = meta.album or info.get("IPRD")
        meta.genre = meta.genre or info.get("IGNR")
        meta.year = meta.year or _parse_year(info.get("ICRD"))

    if meta.duration_ms is None:
        meta.duration_ms = _ffprobe_duration(path)

    _apply_filename_fallback(meta, path)
    return meta


def read_riff_info(path: Path) -> dict[str, str]:
    """Fields of a WAV file's LIST/INFO chunk (INAM title, IART artist, IPRD album, IGNR genre, ICRD date...).

    Walks the RIFF chunk headers with seeks, so the audio data is never read.
    """
    fields: dict[str, str] = {}
    try:
        with path.open("rb") as fh:
            header = fh.read(12)
            if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                return fields
            while chunk := fh.read(8):
                if len(chunk) < 8:
                    break
                chunk_id, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
                if chunk_id == b"LIST" and fh.read(4) == b"INFO":
                    body = fh.read(size - 4)
                    offset = 0
                    while offset + 8 <= len(body):
                        sub_id = body[offset : offset + 4].decode("latin-1")
                        sub_size = struct.unpack("<I", body[offset + 4 : offset + 8])[0]
                        raw = body[offset + 8 : offset + 8 + sub_size].split(b"\0", 1)[0]
                        text = raw.decode("utf-8", "replace").strip()
                        if text:
                            fields[sub_id] = text
                        offset += 8 + sub_size + (sub_size & 1)
                    if size & 1:
                        fh.seek(1, 1)
                else:
                    fh.seek(size + (size & 1) - (4 if chunk_id == b"LIST" else 0), 1)
    except OSError:
        return {}
    return fields
