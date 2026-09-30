import shutil

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Track
from app.services.scanner import scan


def tracks_by_title():
    with SessionLocal() as session:
        return {t.title: t for t in session.scalars(select(Track))}


def test_scan_reads_tags_and_filename_fallback(library):
    result = scan(library)
    assert (result.total, result.added, result.errors) == (3, 3, [])

    tracks = tracks_by_title()
    jet = tracks["Jetsetter"]
    assert jet.artist == "Walker & Royce, Life on Planets"
    assert float(jet.bpm) == 129
    assert (jet.musical_key, jet.camelot_key) == ("Dm", "7A")
    assert jet.rating == 4
    assert 2900 < jet.duration_ms < 3200
    assert len(jet.file_hash) == 64

    assert tracks["For Your Head"].camelot_key == "8A"
    assert tracks["Untagged Groove"].artist == "Artist X"


def test_rescan_skips_unchanged_files(library):
    scan(library)
    result = scan(library)
    assert (result.unchanged, result.added, result.updated) == (3, 0, 0)


def test_moved_file_keeps_its_row_and_user_rating(library):
    scan(library)
    with SessionLocal() as session:
        track = session.scalar(select(Track).where(Track.title == "For Your Head"))
        track_id, track.rating = track.id, 5
        session.commit()

    shutil.move(library / "House" / "b.mp3", library / "moved.mp3")
    result = scan(library)

    assert (result.moved, result.added, result.missing) == (1, 0, 0)
    moved = tracks_by_title()["For Your Head"]
    assert moved.id == track_id
    assert moved.path.endswith("moved.mp3")
    assert moved.rating == 5


def test_missing_files_are_reported_not_deleted(library):
    scan(library)
    (library / "House" / "a.mp3").unlink()
    result = scan(library)
    assert result.missing == 1
    assert "Jetsetter" in tracks_by_title()


def test_application_folders_are_excluded_and_purged(library):
    from tests.conftest import make_mp3

    sampler = make_mp3(library / "Rekordbox" / "Sampler" / "fx.mp3", seconds=1, freq=990)
    scan(library)
    assert "fx" not in tracks_by_title()

    # A row indexed before the exclusion existed is forgotten, the file stays on disk.
    from app.db import SessionLocal
    from app.models import Track

    with SessionLocal() as session:
        session.add(
            Track(
                path=str(sampler), filename="fx.mp3", title="fx", file_hash="x", file_size=1, file_mtime_ns=1
            )
        )
        session.commit()
    result = scan(library)
    assert result.excluded == 1
    assert "fx" not in tracks_by_title()
    assert sampler.exists()
