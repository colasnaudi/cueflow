import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.audio import rhythm
from app.audio.structure import detect_sections
from app.models import Beatgrid, Cue, Track
from app.services import rekordbox
from app.services.cue_engine import plan_cues
from app.services.scanner import scan

FIXTURES = Path(__file__).parent / "fixtures" / "structure"


def wtf_sections():
    data = json.loads((FIXTURES / "broken_hill_wtf_extended_mix.json").read_text())
    return detect_sections(
        np.array(data["features"]), np.array(data["beat_features"]), data["first_bar_beat"]
    )


def hot(cues):
    return [(c.slot, c.label, c.bar + 1, c.beat + 1) for c in cues if c.type == "HOT"]


def test_hot_cues_follow_the_dj_layout_on_a_real_track():
    vocals = [0.1] * 60 + [0.9] * 10 + [0.1] * 78  # voice enters on bar 61
    cues = plan_cues(wtf_sections(), vocals)
    assert hot(cues) == [
        ("A", "START", 1, 1),
        ("B", "GROOVE", 17, 1),
        ("C", "BREAK", 33, 1),
        ("D", "DROP", 49, 1),
        ("E", "VOCAL", 61, 1),
        ("F", "DROP 2", 96, 1),  # the second drop reported by the user: bar 96, 2:59.55
        ("G", "OUTRO", 132, 1),
    ]
    memory = [(c.slot, c.label, c.bar + 1) for c in cues if c.type == "MEMORY"]
    assert memory[0] == ("M01", "INTRO", 1) and memory[-1] == ("M09", "OUTRO", 132)
    assert len(memory) == len(wtf_sections())


def test_no_two_hot_cues_on_the_same_beat_and_no_vocal_in_the_intro():
    sections = [
        SimpleNamespace(
            type="DROP", start_bar=0, start_beat=0, confidence=0.8
        ),  # a track starting on its drop
        SimpleNamespace(type="BREAK", start_bar=32, start_beat=0, confidence=0.8),
        SimpleNamespace(type="DROP", start_bar=48, start_beat=2, confidence=0.8),
    ]
    # The voice is there from bar 1, i.e. on START: no second hot cue on the same beat.
    assert hot(plan_cues(sections, [0.9] * 64)) == [
        ("A", "START", 1, 1),
        ("C", "BREAK", 33, 1),
        ("F", "DROP 2", 49, 3),
    ]

    with_intro = [SimpleNamespace(type="INTRO", start_bar=0, start_beat=0, confidence=0.9), *sections[1:]]
    vocals = [0.9] * 8 + [0.1] * 28 + [0.9] * 28  # a vocal sample in the intro (bars 1-32), the vocal at 37
    assert ("E", "VOCAL", 37, 1) in hot(plan_cues(with_intro, vocals))
    assert plan_cues([]) == []


def grid(bpm=120.0, first_beat=0.5, downbeat_offset=1):
    return Beatgrid(
        bpm=Decimal(bpm), first_beat=Decimal(first_beat), downbeat_offset=downbeat_offset, beats_per_bar=4
    )


def track(path, rating=0):
    return Track(
        path=path,
        filename=Path(path).name,
        title="Été, l'été",
        artist="A & B",
        file_size=1234,
        duration_ms=200_000,
        rating=rating,
        bitrate=320,
        sample_rate=44100,
        musical_key="Am",
    )


def test_rekordbox_xml():
    cues = [
        Cue(slot="D", type="HOT", label="DROP", bar=48, beat=0, color="#E62828"),
        Cue(slot="A", type="HOT", label="START", bar=0, beat=0, color="#28E214"),
        Cue(slot="M01", type="MEMORY", label="INTRO", bar=0, beat=0, color="#28E214"),
    ]
    items = [
        rekordbox.ExportItem(track("/Music/02_GENRES/Été, Mix & Co's.mp3", rating=4), grid(), cues),
        rekordbox.ExportItem(track("/Music/b.wav"), grid(), cues),
    ]
    root = ET.fromstring(rekordbox.build(items, include_beatgrid=True, mp3_offset_ms=26, name="Test"))

    assert root.tag == "DJ_PLAYLISTS" and root.find("COLLECTION").get("Entries") == "2"
    mp3, wav = root.findall("COLLECTION/TRACK")
    assert mp3.get("Location") == "file://localhost/Music/02_GENRES/%C3%89t%C3%A9%2C%20Mix%20%26%20Co%27s.mp3"
    assert (mp3.get("Name"), mp3.get("Kind"), mp3.get("Rating"), mp3.get("AverageBpm")) == (
        "Été, l'été",
        "MP3 File",
        "204",
        "120.00",
    )
    assert wav.get("Rating") is None  # 0 stars would wipe a rating set in Rekordbox

    # Bar 1 = first beat + 1 beat = 0.5 + 0.5 s; MP3s get the 26 ms decoder offset, WAVs do not.
    assert mp3.find("TEMPO").attrib == {"Inizio": "1.026", "Bpm": "120.00", "Metro": "4/4", "Battito": "1"}
    assert wav.find("TEMPO").get("Inizio") == "1.000"
    marks = [
        (m.get("Name"), m.get("Num"), m.get("Start"), m.get("Red")) for m in wav.findall("POSITION_MARK")
    ]
    assert marks == [
        ("START", "0", "1.000", "40"),
        ("DROP", "3", "97.000", "230"),
        ("INTRO", "-1", "1.000", "40"),
    ]

    playlist = root.find("PLAYLISTS/NODE/NODE")
    assert (playlist.get("Name"), playlist.get("Entries")) == ("Test", "2")
    assert [t.get("Key") for t in playlist.findall("TRACK")] == ["1", "2"]

    without_grid = ET.fromstring(rekordbox.build(items, include_beatgrid=False))
    assert without_grid.find("COLLECTION/TRACK/TEMPO") is None


def fake_analysis(**overrides):
    return rhythm.RhythmAnalysis(
        **{
            "bpm": 120.0,
            "first_beat": 0.0,
            "downbeat_offset": 0,
            "beat_count": 400,
            "grid_confidence": 0.9,
            "downbeat_confidence": 0.9,
            "musical_key": "Am",
            "camelot_key": "8A",
            "key_strength": 0.8,
            "energy_curve": [1.0] * 64,
            "sections": [
                {"type": "INTRO", "start_bar": 0, "end_bar": 16, "confidence": 0.9},
                {"type": "BREAK", "start_bar": 16, "end_bar": 32, "confidence": 0.8},
                {
                    "type": "DROP",
                    "start_bar": 32,
                    "end_bar": 64,
                    "start_beat": 0,
                    "end_beat": 0,
                    "confidence": 0.8,
                },
            ],
            "vocal_curve": [0.0] * 64,
            "vocal_probability": 0.0,
            "duration": 128.0,
        }
        | overrides
    )


def test_cue_workflow_and_export(client, library, monkeypatch, tmp_path):
    """Manual review mode (AUTO_APPROVE_CUES=false)."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_approve_cues", False)
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]
    assert client.post(f"/tracks/{track_id}/cues/regenerate").status_code == 409
    assert client.post("/export/rekordbox", json={}).status_code == 422

    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    client.post(f"/tracks/{track_id}/analysis")
    cues = client.get(f"/tracks/{track_id}/cues").json()
    assert [(c["slot"], c["label"], c["bar"]) for c in cues if c["type"] == "HOT"] == [
        ("A", "START", 0),
        ("C", "BREAK", 16),
        ("D", "DROP", 32),
    ]
    assert all(c["source"] == "ANALYSIS" and not c["approved"] for c in cues)

    # Nothing approved yet: the default export has nothing, the preview says what is waiting.
    preview = client.get("/export/rekordbox/preview").json()
    assert (preview["tracks"], preview["unapproved_tracks"]) == (0, 1)

    start = next(c for c in cues if c["slot"] == "A")
    remaining = client.delete(f"/tracks/{track_id}/cues/{start['id']}").json()
    assert "A" not in {c["slot"] for c in remaining}
    approved = client.post(f"/tracks/{track_id}/cues/approve").json()
    assert all(c["approved"] for c in approved)

    # Re-analysis with another drop keeps the approved cues untouched.
    monkeypatch.setattr(
        rhythm,
        "analyse",
        lambda path: fake_analysis(
            sections=[
                {"type": "GROOVE", "start_bar": 0, "end_bar": 40, "confidence": 0.9},
                {"type": "DROP", "start_bar": 40, "end_bar": 64, "confidence": 0.8},
            ]
        ),
    )
    client.post(f"/tracks/{track_id}/analysis")
    after = {c["slot"]: c for c in client.get(f"/tracks/{track_id}/cues").json()}
    assert after["D"]["bar"] == 32 and after["D"]["approved"]
    assert after["A"]["bar"] == 0 and not after["A"]["approved"]  # deleted suggestion comes back, unapproved

    preview = client.get("/export/rekordbox/preview").json()
    assert preview["tracks"] == 1
    response = client.post("/export/rekordbox", json={"approved_only": True})
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="cueflow-rekordbox-')
    root = ET.fromstring(response.content)
    names = [m.get("Name") for m in root.findall("COLLECTION/TRACK/POSITION_MARK")]
    assert "START" not in names and "DROP" in names  # only approved cues
    from app.config import get_settings

    assert len(list((get_settings().data_dir / "exports").glob("*.xml"))) == 1


@pytest.mark.parametrize("folder", ["House", "Nope"])
def test_export_scoped_to_a_folder(client, library, monkeypatch, folder):
    scan(library)
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    for item in client.get("/tracks").json()["items"]:
        client.post(f"/tracks/{item['id']}/analysis")
    count = client.get("/export/rekordbox/preview", params={"folder": folder, "approved_only": False}).json()[
        "tracks"
    ]
    assert count == (2 if folder == "House" else 0)


def test_job_gives_cues_to_tracks_analysed_before_cues_existed(library, monkeypatch):
    from sqlalchemy import delete, select

    from app.db import SessionLocal
    from app.services import analysis

    scan(library)
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    with SessionLocal() as session:
        track = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        analysis.analyse_track(session, track)
        session.execute(delete(Cue))
        session.commit()
        monkeypatch.setattr(
            analysis, "eligible_tracks", lambda session, *args: []
        )  # no audio work in this test
        analysis.run(workers=1)
        assert {c.slot for c in session.scalars(select(Cue).where(Cue.track_id == track.id))} >= {
            "A",
            "C",
            "D",
        }


def test_tracks_without_cues_are_not_exported(client, library, monkeypatch):
    scan(library)
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis(sections=[]))
    track_id = client.get("/tracks").json()["items"][0]["id"]
    client.post(f"/tracks/{track_id}/analysis")
    assert client.get("/export/rekordbox/preview", params={"approved_only": False}).json()["tracks"] == 0


def test_auto_approved_cues_are_exportable_and_refreshed_by_reanalysis(client, library, monkeypatch):
    """Default mode: analysed tracks are ready for Rekordbox; only DJ-validated cues survive re-analysis."""
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    client.post(f"/tracks/{track_id}/analysis")
    cues = client.get(f"/tracks/{track_id}/cues").json()
    assert cues and all(c["approved"] and c["approved_by"] == "AUTO" for c in cues)
    assert client.get("/export/rekordbox/preview").json()["tracks"] == 1

    # A better analysis replaces the automatic cues...
    monkeypatch.setattr(
        rhythm,
        "analyse",
        lambda path: fake_analysis(
            sections=[
                {"type": "GROOVE", "start_bar": 0, "end_bar": 40, "confidence": 0.9},
                {"type": "DROP", "start_bar": 40, "end_bar": 64, "confidence": 0.8},
            ]
        ),
    )
    client.post(f"/tracks/{track_id}/analysis")
    slots = {c["slot"]: c for c in client.get(f"/tracks/{track_id}/cues").json()}
    assert slots["D"]["bar"] == 40 and "C" not in slots

    # ...but not the ones the DJ validated.
    client.post(f"/tracks/{track_id}/cues/approve")
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    client.post(f"/tracks/{track_id}/analysis")
    slots = {c["slot"]: c for c in client.get(f"/tracks/{track_id}/cues").json()}
    assert (slots["D"]["bar"], slots["D"]["approved_by"]) == (40, "USER")


def test_job_approves_cues_generated_before_auto_approval(library, monkeypatch):
    from sqlalchemy import select, update

    from app.db import SessionLocal
    from app.services import analysis

    scan(library)
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    with SessionLocal() as session:
        track = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        analysis.analyse_track(session, track)
        session.execute(update(Cue).values(approved=False, approved_by=None))
        session.commit()
        monkeypatch.setattr(analysis, "eligible_tracks", lambda session, *args: [])
        analysis.run(workers=1)
        assert all(c.approved and c.approved_by == "AUTO" for c in session.scalars(select(Cue)))


def test_folder_scoped_and_forced_audio_analysis(library, monkeypatch):
    """Right-click a folder -> analyse: only that folder; "re-analyse" redoes already analysed tracks."""

    from app.db import SessionLocal
    from app.services import analysis

    make_loop = __import__("tests.test_analysis", fromlist=["write_house_loop"]).write_house_loop
    (library / "Other").mkdir()
    make_loop(library / "House" / "loop.wav", bars=40)
    make_loop(library / "Other" / "loop2.wav", bpm=126.0, bars=40)
    scan(library)
    with SessionLocal() as session:
        assert [t.filename for t in analysis.eligible_tracks(session, "House")] == ["loop.wav"]
    assert analysis.run(workers=1, folder="House").analyzed == 1
    assert analysis.run(workers=1, folder="House").total == 0  # done, unless forced
    assert analysis.run(workers=1, folder="House", force=True).analyzed == 1
    with SessionLocal() as session:
        assert [t.filename for t in analysis.eligible_tracks(session)] == ["loop2.wav"]


def test_live_xml_mirrors_folders_and_is_rewritten_after_analysis(client, library, monkeypatch):
    from app.services import analysis

    scan(library)
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    for item in client.get("/tracks").json()["items"]:
        client.post(f"/tracks/{item['id']}/analysis")
    assert client.get("/export/rekordbox/live").json()["exists"] is True  # each single analysis writes it

    status = client.post("/export/rekordbox/live").json()
    assert (status["exists"], status["tracks"]) == (True, 3)
    root = ET.parse(status["path"]).getroot()
    cueflow = root.find("PLAYLISTS/NODE/NODE")
    names = [n.get("Name") for n in cueflow]
    assert names == ["All analysed tracks", "House"]
    assert cueflow.find("NODE[@Name='All analysed tracks']").get("Entries") == "3"
    assert cueflow.find("NODE[@Name='House']").get("Entries") == "2"  # leaf folder = one playlist

    Path(status["path"]).unlink()
    monkeypatch.setattr(analysis, "eligible_tracks", lambda session, *args: [])
    analysis.run(workers=1)
    assert Path(status["path"]).exists()  # every analysis run refreshes the file Rekordbox reads


def test_reveal_only_opens_library_folders(client, library, monkeypatch):
    import subprocess
    import sys

    opened = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: opened.append(args))
    scan(library)
    assert client.post("/library/reveal", json={"folder": "House"}).status_code == 204
    assert opened == [["open", str((library / "House").resolve())]]
    assert client.post("/library/reveal", json={"folder": "../.."}).status_code == 422
    assert client.post("/library/reveal", json={"folder": "Nope"}).status_code == 422


def test_analysing_one_track_approves_its_cues_and_updates_the_rekordbox_xml(client, library, monkeypatch):
    """One click: analyse -> cues generated, approved and in the XML Rekordbox reads."""
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    client.post(f"/tracks/{track_id}/analysis")

    cues = client.get(f"/tracks/{track_id}/cues").json()
    assert cues and all(c["approved"] for c in cues)
    live = client.get("/export/rekordbox/live").json()
    assert live["exists"]
    marks = ET.parse(live["path"]).getroot().findall("COLLECTION/TRACK/POSITION_MARK")
    assert {m.get("Name") for m in marks} >= {"START", "BREAK", "DROP"}


def test_rekordbox_grid_is_kept_and_cues_snap_onto_it():
    cues = [
        Cue(slot="D", type="HOT", label="DROP", bar=48, beat=0, color="#E62828"),
        Cue(slot="A", type="HOT", label="START", bar=0, beat=0, color="#28E214"),
    ]
    ours = grid()  # 120 BPM, bar 1 at 1.0 s; Rekordbox: same BPM, grid half a beat later (on the kicks)
    item = rekordbox.ExportItem(
        track("/Music/a.wav"), ours, cues, [{"inizio": 0.25, "bpm": 120.0, "battito": "1"}]
    )
    node = ET.fromstring(rekordbox.build([item], include_beatgrid=True, mp3_offset_ms=26)).find(
        "COLLECTION/TRACK"
    )
    assert node.find("TEMPO") is None  # the DJ's grid in Rekordbox is never replaced
    # 1.0 s and 97.0 s are half a beat before Rekordbox's beats (0.25 + k * 0.5): moved forward onto them.
    assert [m.get("Start") for m in node.findall("POSITION_MARK")] == ["1.250", "97.250"]

    other_bpm = rekordbox.ExportItem(track("/Music/b.mp3"), ours, cues, [{"inizio": 0.3, "bpm": 126.0}])
    node = ET.fromstring(rekordbox.build([other_bpm], mp3_offset_ms=26)).find("COLLECTION/TRACK")
    assert node.find("TEMPO") is None  # still not replaced...
    assert node.findall("POSITION_MARK")[0].get("Start") == "1.026"  # ...cues keep Cueflow's own timing

    no_grid = rekordbox.ExportItem(track("/Music/c.wav"), ours, cues)
    assert ET.fromstring(rekordbox.build([no_grid])).find("COLLECTION/TRACK/TEMPO") is not None


def test_playlist_root_count_matches_its_children(library):
    items = [
        rekordbox.ExportItem(
            track(str(library / "House" / "a.mp3")),
            grid(),
            [Cue(slot="A", type="HOT", label="START", bar=0, beat=0)],
        )
    ]
    root = ET.fromstring(rekordbox.build(items, folder_tree=library))
    for node in root.iter("NODE"):
        if node.get("Type") == "0":
            assert int(node.get("Count")) == len(node.findall("NODE")), node.get("Name")
