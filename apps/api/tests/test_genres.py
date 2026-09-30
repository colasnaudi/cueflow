from sqlalchemy import select

from app.audio.styles import ANALYZER_VERSION
from app.db import SessionLocal
from app.models import AudioAnalysis, GenreReview, GenreSuggestion, Track
from app.services import genres
from app.services.genres import build_suggestions
from app.services.scanner import scan
from tests.conftest import make_mp3


def styles(*pairs):
    return [{"style": s, "label": f"Electronic---{s}", "score": score} for s, score in pairs]


def test_suggestions_folder_first_then_audio_with_vocabulary():
    result = build_suggestions(
        "Tech House",
        styles(("Minimal Techno", 0.3), ("tech house", 0.21), ("Techno", 0.1), ("Acid", 0.02)),
        {"techno": "TECHNO"},
    )
    assert [(s["genre"], s["source"], s["rank"]) for s in result] == [
        ("Tech House", "FOLDER+AUDIO", 0),
        ("Minimal Techno", "AUDIO", 1),
        ("TECHNO", "AUDIO", 2),
    ]
    assert result[0]["confidence"] > 0.9


def test_suggestions_without_folder_or_audio():
    assert build_suggestions(None, None, {}) == []
    assert [s["genre"] for s in build_suggestions(None, styles(("House", 0.4)), {})] == ["House"]


def genre_library(library):
    make_mp3(library / "02_GENRES" / "HOUSE" / "TECH_HOUSE" / "t.mp3", seconds=61, title="Folder Track")
    make_mp3(library / "02_GENRES" / "TOOLS" / "VOX" / "v.mp3", seconds=61, freq=300, title="Vox")
    make_mp3(library / "short.mp3", seconds=5, freq=900, title="Short")


def test_job_builds_folder_suggestions_and_skips_samples(library, monkeypatch):
    genre_library(library)
    scan(library)
    monkeypatch.setattr(genres.classifier, "classify", lambda path: styles(("Deep House", 0.3)))

    status = genres.run()
    assert (status.analyzed, status.errors) == (1, [])  # only the 61 s track outside TOOLS

    with SessionLocal() as session:
        track = session.scalar(select(Track).where(Track.title == "Folder Track"))
        suggestions = session.scalars(
            select(GenreSuggestion).where(GenreSuggestion.track_id == track.id).order_by(GenreSuggestion.rank)
        ).all()
        assert [(s.genre, s.source) for s in suggestions] == [
            ("Tech House", "FOLDER"),
            ("Deep House", "AUDIO"),
        ]
        assert session.get(GenreReview, track.id).status == "PENDING"
        assert session.scalar(select(AudioAnalysis.analyzer_version)) == ANALYZER_VERSION
        assert session.scalar(select(GenreReview).join(Track).where(Track.title == "Vox")) is None

    # A second run reuses the stored analysis instead of re-running the model.
    monkeypatch.setattr(
        genres.classifier, "classify", lambda path: (_ for _ in ()).throw(AssertionError("re-analysed"))
    )
    assert genres.run().analyzed == 0


def test_review_approve_reject_reset(client, library, monkeypatch):
    genre_library(library)
    make_mp3(
        library / "copy.mp3", seconds=61, title="Folder Track"
    )  # different bytes? same sine -> same hash
    scan(library)
    monkeypatch.setattr(genres.classifier, "classify", lambda path: styles(("Deep House", 0.3)))
    genres.run()

    page = client.get("/review/genres").json()
    assert page["counts"]["PENDING"] == page["total"] == 1
    item = page["items"][0]
    track_id = item["track"]["id"]
    assert item["folder"] == "02_GENRES/HOUSE/TECH_HOUSE"
    assert [s["genre"] for s in item["suggestions"]] == ["Tech House", "Deep House"]

    body = client.post(f"/review/genres/{track_id}", json={"action": "approve", "genre": "Tech House"}).json()
    assert (body["review"]["status"], body["track"]["genre"], body["review"]["previous_genre"]) == (
        "APPROVED",
        "Tech House",
        None,
    )
    # Identical copies share the approved genre.
    copies = client.get("/tracks", params={"q": "Folder Track"}).json()["items"]
    assert {t["genre"] for t in copies} == {"Tech House"}

    body = client.post(f"/review/genres/{track_id}", json={"action": "reset"}).json()
    assert (body["review"]["status"], body["track"]["genre"]) == ("PENDING", None)

    assert client.post(f"/review/genres/{track_id}", json={"action": "approve"}).status_code == 422
    body = client.post(f"/review/genres/{track_id}", json={"action": "reject"}).json()
    assert body["review"]["status"] == "REJECTED"
    assert client.get("/review/genres", params={"status": "REJECTED"}).json()["total"] == 1


def test_bulk_approve_uses_top_suggestion(client, library, monkeypatch):
    genre_library(library)
    scan(library)
    monkeypatch.setattr(genres.classifier, "classify", lambda path: styles(("Deep House", 0.3)))
    genres.run()
    track_id = client.get("/review/genres").json()["items"][0]["track"]["id"]
    result = client.post("/review/genres/bulk-approve", json={"track_ids": [track_id]}).json()
    assert result["approved"] == 1
    assert client.get(f"/tracks/{track_id}").json()["genre"] == "Tech House"


def test_real_classifier_runs_on_audio(library, monkeypatch):
    """End-to-end Essentia inference with the repo's models (downloaded to data/models on first use)."""
    from app.audio import styles as styles_module
    from app.audio.styles import classifier
    from app.config import REPO_ROOT

    monkeypatch.setattr(styles_module, "models_dir", lambda: REPO_ROOT / "data" / "models")

    path = make_mp3(library / "sine.mp3", seconds=10)
    result = classifier.classify(path, top=5)
    assert len(result) == 5
    assert all(0 <= s["score"] <= 1 and "---" in s["label"] for s in result)


def test_job_states_completed_stopped_failed(library, monkeypatch):
    import pytest

    genre_library(library)
    scan(library)
    monkeypatch.setattr(genres.classifier, "classify", lambda path: styles(("House", 0.3)))
    assert genres.run().state == "completed"

    monkeypatch.setattr(
        genres, "eligible_tracks", lambda session: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    with pytest.raises(RuntimeError):
        genres.run()
    assert (genres.status.state, genres.status.error) == ("failed", "db down")

    monkeypatch.undo()
    monkeypatch.setattr(genres.classifier, "classify", lambda path: styles(("House", 0.3)))
    with SessionLocal() as session:
        session.execute(AudioAnalysis.__table__.delete())
        session.commit()
    original = genres.save_suggestions

    def stop_after_first(*args, **kwargs):
        original(*args, **kwargs)
        genres.request_stop()

    monkeypatch.setattr(genres, "save_suggestions", stop_after_first)
    result = genres.run()
    assert result.state == "stopped"
    assert result.analyzed == 0
