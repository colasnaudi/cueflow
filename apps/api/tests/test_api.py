import shutil

from app.services.scanner import scan


def ids(response):
    assert response.status_code == 200, response.text
    return [t["title"] for t in response.json()["items"]]


def test_search_filters_and_sort(client, library):
    scan(library)
    assert ids(client.get("/tracks", params={"q": "walker royce"})) == ["Jetsetter"]
    assert ids(client.get("/tracks", params={"bpm_min": 125, "bpm_max": 127})) == ["For Your Head"]
    assert ids(client.get("/tracks", params={"key": ["8a", "7A"], "sort": "bpm", "order": "desc"})) == [
        "Jetsetter",
        "For Your Head",
    ]
    assert ids(client.get("/tracks", params={"genre": "tech house"})) == ["Jetsetter"]
    assert client.get("/tracks", params={"limit": 2}).json()["total"] == 3


def test_dedupe_keeps_one_copy_per_hash(client, library):
    shutil.copy(library / "House" / "a.mp3", library / "copy-of-a.mp3")
    scan(library)
    assert client.get("/tracks", params={"q": "jetsetter"}).json()["total"] == 2
    # Regression: the dedupe subquery must not be correlated with the outer query.
    assert client.get("/tracks", params={"q": "jetsetter", "dedupe": True}).json()["total"] == 1
    assert client.get("/tracks", params={"dedupe": True}).json()["total"] == 3


def test_tags_rating_and_key_edit(client, library):
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]

    body = client.post(f"/tracks/{track_id}/tags", json={"name": "#peak time"}).json()
    assert [t["name"] for t in body["tags"]] == ["PEAK_TIME"]
    client.post(f"/tracks/{track_id}/tags", json={"name": "PEAK_TIME"})  # idempotent
    assert ids(client.get("/tracks", params={"tag": "peak_time"})) == ["Jetsetter"]
    assert client.get("/tags").json()[0] | {"id": None} == {
        "id": None,
        "name": "PEAK_TIME",
        "category": None,
        "count": 1,
    }

    tag_id = body["tags"][0]["id"]
    assert client.delete(f"/tracks/{track_id}/tags/{tag_id}").json()["tags"] == []

    body = client.patch(f"/tracks/{track_id}", json={"rating": 5, "musical_key": "F#m"}).json()
    assert (body["rating"], body["musical_key"], body["camelot_key"]) == (5, "F#m", "11A")
    assert client.patch(f"/tracks/{track_id}", json={"musical_key": "H#"}).status_code == 422
    assert client.patch(f"/tracks/{track_id}", json={"rating": 9}).status_code == 422


def test_audio_supports_range_and_peaks_are_cached(client, library):
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]

    audio = client.get(f"/tracks/{track_id}/audio", headers={"Range": "bytes=0-99"})
    assert audio.status_code == 206
    assert audio.headers["content-type"] == "audio/mpeg"
    assert len(audio.content) == 100

    peaks = client.get(f"/tracks/{track_id}/peaks").json()
    assert 2.9 < peaks["duration"] < 3.2
    assert len(peaks["peaks"]) > 100
    assert max(peaks["peaks"]) == 1.0
    assert client.get(f"/tracks/{track_id}/peaks").json() == peaks


def test_facets_and_scan_endpoint(client, library):
    assert client.post("/library/scan", json={"path": str(library / "nope")}).status_code == 422
    scan(library)
    facets = client.get("/library/facets").json()
    assert facets["total"] == 3
    assert {g["value"] for g in facets["genres"]} == {"Tech House", "House"}
    assert [k["value"] for k in facets["keys"]] == ["7A", "8A"]


def test_unknown_track_is_404(client):
    assert client.get("/tracks/00000000-0000-0000-0000-000000000000").status_code == 404


def test_scan_endpoint_only_accepts_folders_inside_music_root(client, library, tmp_path):
    outside = tmp_path / "Elsewhere"
    outside.mkdir()
    assert client.post("/library/scan", json={"path": str(outside)}).status_code == 422
    assert client.post("/library/scan", json={"path": "../Elsewhere"}).status_code == 422
    assert client.post("/library/scan", json={"path": "Nope"}).status_code == 422
    assert client.post("/library/scan", json={"path": "House"}).json()["root"] == str(
        (library / "House").resolve()
    )


def test_scan_status_reports_failure(library, monkeypatch):
    import pytest

    from app.services import scanner

    monkeypatch.setattr(scanner, "find_audio_files", lambda root: (_ for _ in ()).throw(OSError("disk gone")))
    with pytest.raises(OSError):
        scanner.scan(library)
    assert (scanner.status.state, scanner.status.error, scanner.status.running) == (
        "failed",
        "disk gone",
        False,
    )
