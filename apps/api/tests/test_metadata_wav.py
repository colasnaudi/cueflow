import struct
import wave

from sqlalchemy import select

from app.audio.metadata import read_metadata, read_riff_info
from app.db import SessionLocal
from app.models import GenreReview, Track
from app.services.scanner import scan


def write_wav_with_info(path, info: dict[str, str], seconds=1.0):
    """A real WAV, then a LIST/INFO chunk appended after the audio (where Beatport/ffmpeg put it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes(b"\0\0" * int(44100 * seconds))
    body = b"INFO"
    for key, value in info.items():
        raw = value.encode() + b"\0"
        body += key.encode() + struct.pack("<I", len(raw)) + raw + (b"\0" if len(raw) % 2 else b"")
    data = path.read_bytes()
    data += b"LIST" + struct.pack("<I", len(body)) + body
    path.write_bytes(data[:4] + struct.pack("<I", len(data) - 8) + data[8:])
    return path


def test_riff_info_is_read_from_wav_files(tmp_path):
    path = write_wav_with_info(
        tmp_path / "x.wav",
        {
            "INAM": "Can't Let Go",
            "IART": "BLOND:ISH",
            "IPRD": "Nothing Wrong",
            "IGNR": "House",
            "ICRD": "20241115",
        },
    )
    assert read_riff_info(path)["IGNR"] == "House"
    meta = read_metadata(path)
    assert (meta.title, meta.artist, meta.album, meta.genre, meta.year) == (
        "Can't Let Go",
        "BLOND:ISH",
        "Nothing Wrong",
        "House",
        2024,
    )
    assert read_riff_info(tmp_path / "missing.wav") == {}


def test_reread_updates_unchanged_files_but_keeps_approved_genres(library):
    wav = write_wav_with_info(library / "Wav" / "Artist - Track.wav", {"IGNR": "Tech House"})
    scan(library)
    with SessionLocal() as session:
        track = session.scalar(select(Track).where(Track.path == str(wav)))
        track.genre = None  # as if scanned before RIFF INFO was supported
        jet = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        jet.genre = "UK House"
        session.add(GenreReview(track_id=jet.id, status="APPROVED", chosen_genre="UK House"))
        session.commit()

    assert scan(library).updated == 0  # unchanged files are skipped...
    result = scan(library, reread=True)  # ...unless asked to re-read their tags
    assert result.updated >= 1
    with SessionLocal() as session:
        assert session.scalar(select(Track.genre).where(Track.path == str(wav))) == "Tech House"
        assert session.scalar(select(Track.genre).where(Track.title == "Jetsetter")) == "UK House"
