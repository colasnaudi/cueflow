import os
import subprocess
from pathlib import Path

import pytest
from mutagen.id3 import ID3, POPM, TBPM, TCON, TIT2, TKEY, TPE1

TEST_DB = "cueflow_test"
ADMIN_URL = "postgresql+psycopg://cueflow:cueflow@localhost:5433/cueflow"
os.environ["DATABASE_URL"] = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")
    yield
    from app.db import engine

    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))


@pytest.fixture(autouse=True)
def clean_tables(database, tmp_path, monkeypatch):
    from app.config import get_settings
    from app.db import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE tracks, tags CASCADE"))
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path / "data")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def make_mp3(path: Path, *, seconds: float = 3.0, freq: int = 440, **tags) -> Path:
    """Render a short sine MP3 with ffmpeg, then write ID3 tags (title, artist, bpm, key, genre, popm)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration={seconds}",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
    )
    id3 = ID3()
    frames = {"title": TIT2, "artist": TPE1, "bpm": TBPM, "key": TKEY, "genre": TCON}
    for name, frame in frames.items():
        if name in tags:
            id3.add(frame(encoding=3, text=str(tags[name])))
    if "popm" in tags:
        id3.add(POPM(email="", rating=tags["popm"], count=0))
    id3.save(path)
    return path


@pytest.fixture
def trash(tmp_path, monkeypatch):
    """Replace the macOS Trash with a folder so tests never touch the real one."""
    bin_dir = tmp_path / "Trash"
    bin_dir.mkdir()

    def fake_send2trash(path):
        Path(path).rename(bin_dir / Path(path).name)

    monkeypatch.setattr("app.services.cleanup.send2trash", fake_send2trash)
    return bin_dir


@pytest.fixture
def library(tmp_path, monkeypatch):
    from app.config import get_settings

    root = tmp_path / "Music"
    monkeypatch.setattr(get_settings(), "music_root", str(root))
    make_mp3(
        root / "House" / "a.mp3",
        title="Jetsetter",
        artist="Walker & Royce/Life on Planets",
        bpm="129",
        key="7A",
        genre="Tech House",
        popm=196,
    )
    make_mp3(
        root / "House" / "b.mp3",
        freq=550,
        title="For Your Head",
        artist="Someone",
        bpm="126",
        key="Am",
        genre="House",
    )
    make_mp3(root / "Artist X - Untagged Groove.mp3", freq=660)
    return root
