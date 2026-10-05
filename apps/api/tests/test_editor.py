import hashlib
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.models import Track
from app.schemas import EditList
from app.services.editor import render
from app.services.scanner import scan


def edit(*segments, gain_db=0.0, rate=44_100):
    return {"sample_rate": rate, "gain_db": gain_db, "segments": [dict(s) for s in segments]}


def seg(start, end, ramps=()):
    return {"start": start, "end": end, "ramps": [list(r) for r in ramps]}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return float(out.stdout)


@pytest.fixture
def track_id(library, client):
    from app.db import SessionLocal

    scan(library)
    with SessionLocal() as session:
        track = session.query(Track).filter(Track.filename == "a.mp3").one()
        return str(track.id)


@pytest.fixture
def edits(tmp_path, monkeypatch):
    from app.config import get_settings

    folder = tmp_path / "Edits"
    monkeypatch.setattr(get_settings(), "edits_dir", str(folder))
    return folder


def test_render_rearranges_segments_and_applies_ramps_and_gain():
    audio = np.stack([np.arange(10, dtype=np.float32)] * 2, axis=1)
    out = render(
        audio, EditList.model_validate(edit(seg(6, 8), seg(0, 2), seg(0, 4, [(0, 1)]), gain_db=-6.0206))
    )
    left = out[:, 0]
    assert np.allclose(left[:4], [3, 3.5, 0, 0.5], atol=1e-3)  # 6, 7, 0, 1 at half gain
    assert np.allclose(left[4:], np.array([0, 1, 2, 3]) * [0, 0.25, 0.5, 0.75] * 0.5, atol=1e-3)


def test_render_refuses_a_segment_past_the_end():
    audio = np.zeros((10, 2), dtype=np.float32)
    with pytest.raises(Exception, match="frame 20"):
        render(audio, EditList.model_validate(edit(seg(0, 20))))


@pytest.mark.parametrize(
    "body",
    [
        edit(),  # no segment
        edit(seg(10, 5)),  # ends before it starts
        edit(seg(0, 5, [(0, 2)])),  # ramp gain above 1
        edit(seg(0, 5), gain_db=60),
    ],
)
def test_invalid_edit_lists_are_rejected(client, track_id, body):
    assert client.put(f"/tracks/{track_id}/edit", json=body).status_code == 422


def test_working_edit_is_saved_and_reset_without_touching_the_file(client, track_id, library):
    original = library / "House" / "a.mp3"
    before = digest(original)
    empty = client.get(f"/tracks/{track_id}/edit").json()
    assert empty["edit"] is None and empty["sample_rate"] == 44_100

    body = edit(seg(0, 44_100), seg(88_200, 132_300, [(1, 0)]), gain_db=-3)
    saved = client.put(f"/tracks/{track_id}/edit", json=body)
    assert saved.status_code == 200
    assert client.get(f"/tracks/{track_id}/edit").json()["edit"] == body

    assert client.delete(f"/tracks/{track_id}/edit").json()["edit"] is None
    assert client.get(f"/tracks/{track_id}/edit").json()["edit"] is None
    assert digest(original) == before


def test_edit_at_another_sample_rate_is_rejected(client, track_id):
    response = client.put(f"/tracks/{track_id}/edit", json=edit(seg(0, 100), rate=48_000))
    assert response.status_code == 422


def test_source_is_the_decoded_original_as_wav(client, track_id):
    response = client.get(f"/tracks/{track_id}/edit/source")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"


def test_export_writes_a_new_file_and_never_overwrites(client, track_id, library, edits):
    original = library / "House" / "a.mp3"
    before = digest(original)
    body = {"edit": edit(seg(0, 44_100), seg(0, 44_100, [(1, 0)])), "format": "wav", "quality": 16}

    first = client.post(f"/tracks/{track_id}/edit/export", json=body).json()
    assert first["filename"] == "a (Edited).wav" and first["duration_ms"] == 2000
    assert Path(first["path"]).parent == edits
    assert duration(Path(first["path"])) == pytest.approx(2.0, abs=0.01)
    first_digest = digest(Path(first["path"]))

    second = client.post(
        f"/tracks/{track_id}/edit/export", json={**body, "format": "mp3", "quality": 320}
    ).json()
    third = client.post(f"/tracks/{track_id}/edit/export", json=body).json()
    assert second["filename"] == "a (Edited).mp3"
    assert third["filename"] == "a (Edited 2).wav"
    assert digest(Path(first["path"])) == first_digest  # the earlier export is untouched
    assert digest(original) == before
    assert sorted(p.name for p in edits.iterdir()) == ["a (Edited 2).wav", "a (Edited).mp3", "a (Edited).wav"]


def test_export_keeps_the_original_tags(client, track_id, edits):
    body = {"edit": edit(seg(0, 44_100)), "format": "mp3", "quality": 192}
    path = client.post(f"/tracks/{track_id}/edit/export", json=body).json()["path"]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=title", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert out.stdout.strip() == "Jetsetter"


def test_export_quality_must_match_the_format(client, track_id, edits):
    body = {"edit": edit(seg(0, 44_100)), "format": "wav", "quality": 320}
    assert client.post(f"/tracks/{track_id}/edit/export", json=body).status_code == 422
    assert not edits.exists()


def test_export_past_the_end_creates_no_file(client, track_id, edits):
    body = {"edit": edit(seg(0, 44_100 * 60)), "format": "wav", "quality": 16}
    assert client.post(f"/tracks/{track_id}/edit/export", json=body).status_code == 422
    assert not edits.exists() or not any(edits.iterdir())
