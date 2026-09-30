import shutil

from app.services.cleanup import normalize_title
from app.services.scanner import scan
from tests.conftest import make_mp3


def test_exact_duplicates_keep_organised_copy_and_merge_user_data(client, library, trash):
    organised = library / "02_GENRES" / "HOUSE" / "a.mp3"
    organised.parent.mkdir(parents=True)
    shutil.copy(library / "House" / "a.mp3", organised)
    scan(library)

    page = client.get("/cleanup/duplicates").json()
    assert (page["total_groups"], page["removable_files"]) == (1, 1)
    group = page["groups"][0]
    by_folder = {c["folder"]: c["track"]["id"] for c in group["copies"]}
    assert group["keep_ids"] == [by_folder["02_GENRES/HOUSE"]]
    keep_id = group["keep_ids"][0]

    loose = by_folder["House"]
    client.patch(f"/tracks/{loose}", json={"rating": 5})
    client.post(f"/tracks/{loose}/tags", json={"name": "banger"})

    result = client.post(
        "/cleanup/duplicates/resolve", json={"keep_id": keep_id, "remove_ids": [loose]}
    ).json()
    assert (result["removed"], result["errors"]) == (1, [])
    assert result["freed_bytes"] > 0
    assert not (library / "House" / "a.mp3").exists()
    assert (trash / "a.mp3").exists()

    kept = client.get(f"/tracks/{keep_id}").json()
    assert kept["rating"] == 5
    assert [t["name"] for t in kept["tags"]] == ["BANGER"]
    assert client.get("/cleanup/duplicates").json()["total_groups"] == 0


def test_resolve_rejects_keeping_and_removing_same_track(client, library, trash):
    scan(library)
    track_id = client.get("/tracks").json()["items"][0]["id"]
    response = client.post(
        "/cleanup/duplicates/resolve", json={"keep_id": track_id, "remove_ids": [track_id]}
    )
    assert response.status_code == 422


def test_resolve_all_exact(client, library, trash):
    shutil.copy(library / "House" / "a.mp3", library / "a-copy.mp3")
    shutil.copy(library / "House" / "b.mp3", library / "b-copy.mp3")
    scan(library)
    result = client.post("/cleanup/duplicates/resolve-all").json()
    assert result["removed"] == 2
    assert client.get("/tracks").json()["total"] == 3


def test_probable_duplicates(client, library, trash):
    make_mp3(library / "x1.mp3", seconds=61, freq=400, title="Get Down (Original Mix)", artist="Sambo")
    make_mp3(library / "x2.mp3", seconds=62, freq=410, title="Get Down", artist="SAMBO")
    make_mp3(library / "x3.mp3", seconds=90, freq=420, title="Get Down", artist="Sambo")  # other version
    scan(library)
    page = client.get("/cleanup/duplicates", params={"kind": "probable"}).json()
    assert page["total_groups"] == 1
    assert sorted(c["track"]["filename"] for c in page["groups"][0]["copies"]) == ["x1.mp3", "x2.mp3"]
    assert normalize_title("Beyoncé – Crazy (Extended Mix)") == "beyonce crazy"


def test_short_tracks_grouped_by_folder(client, library, trash):
    for i in range(3):
        make_mp3(library / "02_GENRES" / "TOOLS" / "VOX" / f"v{i}.mp3", seconds=2, freq=300 + i)
    make_mp3(library / "Inbox" / "s.mp3", seconds=2, freq=800)
    scan(library)

    short = client.get("/cleanup/short", params={"max_ms": 2_500}).json()
    assert short["total"] == 4
    assert [(f["folder"], f["count"], f["sample_folder"]) for f in short["folders"]] == [
        ("02_GENRES/TOOLS/VOX", 3, True),
        ("Inbox", 1, False),
    ]
    assert len(client.get("/cleanup/short/tracks", params={"folder": "Inbox", "max_ms": 2_500}).json()) == 1

    result = client.post("/cleanup/short/delete", json={"max_ms": 2_500, "folders": ["Inbox"]}).json()
    assert result["removed"] == 1
    assert client.get("/cleanup/short", params={"max_ms": 2_500}).json()["total"] == 3
    # Tracks longer than the threshold are never touched.
    assert client.get("/tracks", params={"min_duration_ms": 2_500}).json()["total"] == 3


def test_trash_refuses_files_outside_music_root(client, library, trash, tmp_path):
    scan(library)
    from app.db import SessionLocal
    from app.models import Track

    with SessionLocal() as session:
        track = session.query(Track).first()
        track.path = str(tmp_path / "elsewhere.mp3")
        session.commit()
        track_id = str(track.id)
    result = client.post("/cleanup/delete", json={"track_ids": [track_id]}).json()
    assert result["removed"] == 0
    assert "outside the music folder" in result["errors"][0]


def test_probable_groups_ignore_byte_identical_copies(client, library, trash):
    make_mp3(library / "x1.mp3", seconds=61, freq=400, title="Solo", artist="A")
    shutil.copy(library / "x1.mp3", library / "x1-copy.mp3")
    scan(library)
    assert client.get("/cleanup/duplicates", params={"kind": "probable"}).json()["total_groups"] == 0


def test_copies_in_several_genre_folders_and_apple_music_are_kept(client, library, trash):
    """The same track deliberately filed under TECH_HOUSE and UK_HOUSE must survive "resolve all"."""
    source = library / "House" / "a.mp3"
    for folder in ["02_GENRES/HOUSE/TECH_HOUSE", "02_GENRES/HOUSE/UK_HOUSE", "Music/Media.localized/Music/X"]:
        (library / folder).mkdir(parents=True)
        shutil.copy(source, library / folder / "a.mp3")
    scan(library)

    group = client.get("/cleanup/duplicates").json()["groups"][0]
    kept = {c["folder"] for c in group["copies"] if c["track"]["id"] in group["keep_ids"]}
    assert kept == {"02_GENRES/HOUSE/TECH_HOUSE", "02_GENRES/HOUSE/UK_HOUSE", "Music/Media.localized/Music/X"}
    assert [c["protected"] for c in group["copies"] if "Media.localized" in c["folder"]] == [True]

    result = client.post("/cleanup/duplicates/resolve-all").json()
    assert result["removed"] == 1
    assert not source.exists()
    assert (library / "Music/Media.localized/Music/X/a.mp3").exists()

    # Even an explicit request never trashes a file managed by Apple Music.
    apple = next(c["track"]["id"] for c in group["copies"] if c["protected"])
    tech = next(c["track"]["id"] for c in group["copies"] if c["folder"].endswith("TECH_HOUSE"))
    result = client.post("/cleanup/duplicates/resolve", json={"keep_id": tech, "remove_ids": [apple]}).json()
    assert result["removed"] == 0 and "Apple Music" in result["errors"][0]
