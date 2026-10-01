import io
import unicodedata
from urllib.parse import quote

from sqlalchemy import select

from app.db import SessionLocal
from app.models import RekordboxTrack, Track
from app.services.rekordbox_import import decode_location, import_collection
from app.services.scanner import scan
from tests.conftest import make_mp3


def collection(*tracks: dict) -> io.BytesIO:
    rows = []
    for t in tracks:
        attrs = " ".join(f'{k}="{v}"' for k, v in t.items() if k not in ("tempo", "marks"))
        children = "".join(
            f'<TEMPO Inizio="{i}" Bpm="{b}" Metro="4/4" Battito="1"/>' for i, b in t.get("tempo", [])
        ) + "".join(
            f'<POSITION_MARK Name="{n}" Type="0" Start="{s}" Num="{num}"/>'
            for n, s, num in t.get("marks", [])
        )
        rows.append(f"<TRACK {attrs}>{children}</TRACK>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><DJ_PLAYLISTS Version="1.0.0"><PRODUCT Name="rekordbox"/>'
        f'<COLLECTION Entries="{len(rows)}">{"".join(rows)}</COLLECTION>'
        '<PLAYLISTS><NODE Type="0" Name="ROOT">'
        '<NODE Type="1" Name="p" KeyType="0"><TRACK Key="1"/></NODE></NODE>'
        "</PLAYLISTS></DJ_PLAYLISTS>"
    )
    return io.BytesIO(xml.encode())


def location(path) -> str:
    # Rekordbox writes decomposed accents on macOS sometimes: use NFD to prove the match is normalised.
    return "file://localhost" + quote(unicodedata.normalize("NFD", str(path)), safe="/")


def test_decode_location():
    assert (
        decode_location("file://localhost/Users/me/Music/Caf%C3%A9%20%26%20Co.mp3")
        == "/Users/me/Music/Café & Co.mp3"
    )


def test_import_ratings_bpm_key_genre_and_snapshot(library):
    accented = make_mp3(library / "Été" / "Café.mp3", title="Café", popm=196)  # 4 stars in the file tag
    scan(library)
    with SessionLocal() as session:
        jet = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        user = session.scalar(select(Track).where(Track.title == "For Your Head"))
        user.rating, user.rating_source = 2, "USER"  # set in Cueflow: never replaced
        session.commit()
        jet_path, user_path = jet.path, user.path
    untagged = next(p for p in library.rglob("*.mp3") if "Untagged" in p.name)

    source = collection(
        {
            "TrackID": 1,
            "Location": location(jet_path),
            "Rating": 255,
            "Genre": "Ignored: tag genre exists",
            "AverageBpm": "129.00",
            "Tonality": "Fm",
            "tempo": [(0.312, 129.0)],
            "marks": [("DROP", 61.2, 3), ("M", 0.3, -1)],
        },
        {"TrackID": 2, "Location": location(user_path), "Rating": 204},
        {"TrackID": 3, "Location": location(accented), "Rating": 51},
        {
            "TrackID": 4,
            "Location": location(untagged),
            "Rating": 0,
            "Genre": "UK House",
            "AverageBpm": "131.00",
            "Tonality": "11A",
        },
        {"TrackID": 5, "Location": "file://localhost/Users/me/Music/rekordbox/Sampler/HORN.wav", "Rating": 0},
    )
    with SessionLocal() as session:
        summary = import_collection(session, source)
    assert summary == {
        "entries": 5,
        "matched": 4,
        "unmatched": 1,
        "with_hot_cues": 1,
        "ratings": 2,
        "genres": 1,
        "bpms": 1,
        "keys": 1,
    }

    with SessionLocal() as session:
        get = lambda title: session.scalar(select(Track).where(Track.title == title))  # noqa: E731
        assert (get("Jetsetter").rating, get("Jetsetter").rating_source) == (5, "REKORDBOX")
        assert (float(get("Jetsetter").bpm), get("Jetsetter").bpm_source) == (129.0, "TAG")  # tags kept
        assert (get("For Your Head").rating, get("For Your Head").rating_source) == (2, "USER")
        assert (get("Café").rating, get("Café").rating_source) == (1, "REKORDBOX")  # beats the 4-star tag
        untagged_track = get("Untagged Groove")
        assert (untagged_track.genre, float(untagged_track.bpm), untagged_track.bpm_source) == (
            "UK House",
            131.0,
            "REKORDBOX",
        )
        assert (untagged_track.camelot_key, untagged_track.key_source) == ("11A", "REKORDBOX")
        snapshot = session.scalar(
            select(RekordboxTrack).where(RekordboxTrack.track_id == get("Jetsetter").id)
        )
        assert snapshot.tempo == [{"inizio": 0.312, "bpm": 129.0, "battito": "1"}]
        assert [m["num"] for m in snapshot.position_marks] == ["3", "-1"]
        assert session.scalar(
            select(RekordboxTrack).where(RekordboxTrack.track_id.is_(None))
        ).location.endswith("HORN.wav")

    # Re-importing is idempotent; a track un-rated in Rekordbox since loses the imported rating.
    with SessionLocal() as session:
        again = import_collection(
            session, collection({"TrackID": 1, "Location": location(jet_path), "Rating": 0})
        )
    assert again["ratings"] == 1
    with SessionLocal() as session:
        jet = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        assert (jet.rating, jet.rating_source) == (0, None)
        assert session.scalar(select(RekordboxTrack).where(RekordboxTrack.track_id == jet.id)).rating == 0


def test_rescan_never_replaces_a_rekordbox_or_user_rating(library):
    scan(library)
    with SessionLocal() as session:
        jet = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        jet.rating, jet.rating_source = 5, "REKORDBOX"
        session.commit()
    (library / "House" / "a.mp3").touch()
    scan(library)
    scan(library, reread=True)
    with SessionLocal() as session:
        jet = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        assert (jet.rating, jet.rating_source) == (5, "REKORDBOX")


def test_rating_from_the_file_tag_is_marked_tag_and_cueflow_edits_are_user(client, library):
    scan(library)
    jet = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]
    with SessionLocal() as session:
        assert session.scalar(select(Track.rating_source).where(Track.title == "Jetsetter")) == "TAG"
    client.patch(f"/tracks/{jet['id']}", json={"rating": 3})
    with SessionLocal() as session:
        assert session.scalar(select(Track.rating_source).where(Track.title == "Jetsetter")) == "USER"


def test_import_api(client, library):
    scan(library)
    jet_path = next(p for p in library.rglob("a.mp3"))
    body = collection({"TrackID": 1, "Location": location(jet_path), "Rating": 153, "marks": [("A", 0.1, 0)]})
    assert client.post("/rekordbox/import", content=b"not xml").status_code == 422
    assert client.post("/rekordbox/import", content=body.getvalue()).json()["ratings"] == 1
    status = client.get("/rekordbox/import").json()
    assert (status["entries"], status["matched"], status["rated"]) == (1, 1, 1)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]
    snapshot = client.get(f"/rekordbox/tracks/{track_id}").json()
    assert (snapshot["rating"], snapshot["hot_cues"]) == (3, 1)
    assert client.get("/rekordbox/grids").status_code == 200
