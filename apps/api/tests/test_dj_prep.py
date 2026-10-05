"""Editor V2, lot 1: tempo map, DJ beatgrid, sections, cues/loops, notes, and edits joining the catalogue."""

import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest

from app.audio import rhythm
from app.models import Beatgrid, Cue
from app.schemas import EditList
from app.services import rekordbox
from app.services.edit_catalogue import carry_grid, map_forward, map_time, pieces
from app.services.scanner import scan
from app.services.tempo import Anchor, TempoMap, anchors_of, store
from tests.test_cues import fake_analysis, grid, track


@pytest.mark.parametrize("offset", [0, 1, 2, 3])
def test_a_constant_grid_maps_like_the_bar_formula(offset):
    constant = grid(bpm=124.0, first_beat=0.37, downbeat_offset=offset)
    tempo = TempoMap.of(constant)
    period = 60 / 124
    for bar, beat in [(0, 0), (0, 3), (12, 2), (-1, 1)]:
        expected = 0.37 + (offset + bar * 4 + beat) * period
        assert tempo.time_of(bar, beat) == pytest.approx(expected)
        assert tempo.position_of(expected + 0.01) == (bar, beat)
    stored = Beatgrid()
    store(stored, anchors_of(constant))
    assert (float(stored.first_beat), stored.downbeat_offset, stored.anchors) == (0.37, offset, None)


def test_tempo_changes_and_phase_jumps():
    # 120 BPM from 0 s (bar 1 on beat 1), 130 BPM from 8 s (bar 5), then a jump: the beat at 20 s is a beat 3.
    tempo = TempoMap([Anchor(0, 120, 1), Anchor(8, 130, 1), Anchor(20, 130, 3)])
    assert tempo.time_of(4, 0) == pytest.approx(8)
    assert tempo.time_of(5, 0) == pytest.approx(8 + 4 * 60 / 130)
    assert tempo.bpm_at(9) == 130
    bar, beat = tempo.position_of(20)
    assert beat == 2  # beat 3 of its bar
    assert tempo.time_of(bar, beat) == pytest.approx(20)
    assert tempo.time_of(bar, beat + 0.5) == pytest.approx(20 + 30 / 130)  # half a beat later (loop ends)


def test_rekordbox_xml_with_a_dj_grid_and_loops():
    dj = grid()
    store(dj, [Anchor(0.5, 120, 2), Anchor(60.5, 128, 1)])
    dj.source = "USER"
    cues = [
        Cue(slot="A", type="HOT", label="LOOP IN", bar=0, beat=0, loop_beats=Decimal(4)),
        Cue(slot="U01", type="MEMORY", label="BRK", bar=2, beat=0, loop_beats=Decimal("0.5")),
        Cue(slot="B", type="HOT", label="DROP", bar=0, beat=0),
    ]
    theirs = [{"inizio": 0.25, "bpm": 120.0, "battito": "1"}]  # the DJ's grid in Rekordbox: replaced
    item = rekordbox.ExportItem(track("/Music/a.wav"), dj, cues, theirs)
    node = ET.fromstring(rekordbox.build([item])).find("COLLECTION/TRACK")
    tempo = [(t.get("Inizio"), t.get("Bpm"), t.get("Battito")) for t in node.findall("TEMPO")]
    assert tempo == [("0.500", "120.00", "2"), ("60.500", "128.00", "1")]
    marks = {m.get("Name"): m.attrib for m in node.findall("POSITION_MARK")}
    # The beat at 0.5 s is a beat 2: bar 1 starts 3 beats later, at 2.0 s.
    loop = marks["LOOP IN"]
    assert (loop["Type"], loop["Start"], loop["End"], loop["Num"]) == ("4", "2.000", "4.000", "0")
    assert (marks["BRK"]["Start"], marks["BRK"]["End"], marks["BRK"]["Num"]) == ("6.000", "6.250", "-1")
    assert marks["DROP"]["Type"] == "0" and "End" not in marks["DROP"]


@pytest.fixture
def analysed(client, library, monkeypatch):
    monkeypatch.setattr(rhythm, "analyse", lambda path: fake_analysis())
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]
    client.post(f"/tracks/{track_id}/analysis")
    return track_id


def test_dj_grid_survives_reanalysis_and_sets_the_bpm(client, analysed):
    body = {"anchors": [{"time": 0.25, "bpm": 126, "beat": 1}, {"time": 30, "bpm": 128, "beat": 1}]}
    grid = client.put(f"/tracks/{analysed}/beatgrid", json=body).json()["beatgrid"]
    assert grid["source"] == "USER" and grid["bpm"] == 126 and len(grid["anchors"]) == 2
    assert client.get(f"/tracks/{analysed}").json()["bpm"] == 126

    client.post(f"/tracks/{analysed}/analysis")
    assert client.get(f"/tracks/{analysed}/analysis").json()["beatgrid"]["anchors"] == grid["anchors"]

    # Moving bar 1 rotates every anchor; a re-analysis asked to reset the grid drops the tempo changes.
    shifted = client.post(f"/tracks/{analysed}/beatgrid/shift", json={"beats": 1}).json()["beatgrid"]
    assert [a["beat"] for a in shifted["anchors"]] == [4, 4]
    reset = client.post(f"/tracks/{analysed}/analysis", params={"reset_grid": True}).json()["beatgrid"]
    assert reset["anchors"] is None and reset["source"] == "ANALYSIS"


@pytest.mark.parametrize(
    "anchors",
    [
        [],
        [{"time": 1, "bpm": 300, "beat": 1}],
        [{"time": 1, "bpm": 120, "beat": 1}, {"time": 1.05, "bpm": 121, "beat": 1}],
    ],
)
def test_invalid_grids_are_rejected(client, analysed, anchors):
    assert client.put(f"/tracks/{analysed}/beatgrid", json={"anchors": anchors}).status_code == 422


def test_dj_sections_take_precedence_and_can_be_restored(client, analysed):
    detected = [s["type"] for s in client.get(f"/tracks/{analysed}/analysis").json()["sections"]]
    assert detected == ["INTRO", "BREAK", "DROP"]
    mine = [
        {"type": "INTRO", "start_bar": 0, "end_bar": 8},
        {"type": "CUSTOM", "label": "Acapella", "color": "#22cc88", "start_bar": 8, "end_bar": 24},
        {"type": "DROP", "start_bar": 24, "end_bar": 64},
    ]
    sections = client.put(f"/tracks/{analysed}/sections", json={"sections": mine}).json()["sections"]
    assert [(s["type"], s["label"], s["source"]) for s in sections] == [
        ("INTRO", None, "USER"),
        ("CUSTOM", "Acapella", "USER"),
        ("DROP", None, "USER"),
    ]
    client.post(f"/tracks/{analysed}/analysis")  # re-analysis keeps them
    assert len(client.get(f"/tracks/{analysed}/analysis").json()["sections"]) == 3
    assert client.get(f"/tracks/{analysed}/analysis").json()["sections"][1]["label"] == "Acapella"
    # Cue suggestions follow the DJ's sections: the drop moved to bar 25.
    client.post(f"/tracks/{analysed}/cues/regenerate")
    drop = next(c for c in client.get(f"/tracks/{analysed}/cues").json() if c["slot"] == "D")
    assert drop["bar"] == 24

    restored = client.delete(f"/tracks/{analysed}/sections").json()["sections"]
    assert [s["type"] for s in restored] == detected


@pytest.mark.parametrize(
    "sections",
    [
        [{"type": "DROP", "start_bar": 8, "end_bar": 8}],
        [{"type": "DROP", "start_bar": 0, "end_bar": 8}, {"type": "BREAK", "start_bar": 4, "end_bar": 12}],
        [{"type": "SOLO", "start_bar": 0, "end_bar": 8}],
        [{"type": "DROP", "start_bar": 0, "end_bar": 8, "color": "red"}],
    ],
)
def test_invalid_sections_are_rejected(client, analysed, sections):
    assert client.put(f"/tracks/{analysed}/sections", json={"sections": sections}).status_code == 422


def test_dj_cues_and_loops(client, analysed):
    url = f"/tracks/{analysed}/cues"
    generated = {c["slot"] for c in client.get(url).json() if c["type"] == "HOT"}
    created = client.post(url, json={"type": "HOT", "bar": 3, "beat": 2, "label": "Vox", "color": "#ff0000"})
    assert created.status_code == 201
    mine = [c for c in created.json() if c["source"] == "USER"]
    assert len(mine) == 1 and mine[0]["slot"] == next(s for s in "ABCDEFGH" if s not in generated)

    loop = client.post(url, json={"type": "MEMORY", "bar": 8, "loop_beats": 0.5}).json()
    memory_loop = next(c for c in loop if c["loop_beats"] == 0.5)
    assert memory_loop["slot"] == "U01" and memory_loop["type"] == "MEMORY"

    taken = next(iter(generated))
    assert client.post(url, json={"type": "HOT", "bar": 1, "slot": taken}).status_code == 409

    # Moving a generated cue makes it the DJ's: re-analysis does not bring it back.
    drop = next(c for c in client.get(url).json() if c["slot"] == "D")
    moved = client.patch(
        f"{url}/{drop['id']}", json={"bar": 40, "beat": 1, "label": "BIG DROP", "loop_beats": 8}
    )
    after = next(c for c in moved.json() if c["slot"] == "D")
    assert (after["bar"], after["beat"], after["label"], after["loop_beats"], after["approved_by"]) == (
        40, 1, "BIG DROP", 8, "USER",
    )  # fmt: skip
    client.post(f"/tracks/{analysed}/analysis")
    assert next(c for c in client.get(url).json() if c["slot"] == "D")["bar"] == 40
    assert client.patch(f"{url}/{drop['id']}", json={"slot": taken}).status_code == 409
    assert client.patch(f"{url}/{drop['id']}", json={"bar": None}).status_code == 200  # ignored, not cleared

    for slot in "ABCDEFGH":  # fill every hot cue slot
        client.post(url, json={"type": "HOT", "bar": 2, "slot": slot})
    assert client.post(url, json={"type": "HOT", "bar": 2}).status_code == 409


def test_annotations(client, analysed):
    url = f"/tracks/{analysed}/annotations"
    notes = client.post(url, json={"bar": 16, "kind": "WARNING", "text": "Long break"}).json()
    client.post(url, json={"bar": 4, "beat": 2, "text": "Vocal in"})
    notes = client.get(url).json()
    assert [(n["bar"], n["kind"], n["text"]) for n in notes] == [
        (4, "NOTE", "Vocal in"),
        (16, "WARNING", "Long break"),
    ]
    edited = client.patch(f"{url}/{notes[1]['id']}", json={"kind": "FIRE"}).json()
    assert edited[1]["kind"] == "FIRE" and edited[1]["text"] == "Long break"
    assert client.post(url, json={"bar": 1, "kind": "LOL"}).status_code == 422
    assert len(client.delete(f"{url}/{notes[0]['id']}").json()) == 1
    assert client.delete(f"{url}/{notes[0]['id']}").status_code == 404


def edit_list(*segments):
    return EditList.model_validate(
        {"sample_rate": 1000, "segments": [{"start": s, "end": e} for s, e in segments]}
    )


def test_cut_on_the_grid_keeps_one_tempo_and_a_cut_off_the_grid_adds_an_anchor():
    tempo = TempoMap([Anchor(0, 120, 1)])  # beats every 0.5 s, bars every 2 s
    on_grid = pieces(edit_list((0, 4000), (8000, 20000)))  # bars 3-4 removed
    assert carry_grid(tempo, on_grid) == [Anchor(0, 120, 1)]

    off_grid = pieces(edit_list((0, 4000), (8250, 20000)))  # cut lands a quarter beat after a downbeat
    anchors = carry_grid(tempo, off_grid)
    assert anchors[0] == Anchor(0, 120, 1)
    assert anchors[1].time == pytest.approx(4.25) and anchors[1].beat == 2  # original 8.5 s: beat 2

    assert map_time(off_grid, 9) == pytest.approx(4.75)
    assert map_time(off_grid, 5) is None  # cut
    assert map_forward(off_grid, 5) == pytest.approx(4.0)  # next heard material


def test_exported_edit_joins_the_catalogue_with_its_preparation(client, analysed, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "edits_dir", str(tmp_path / "Edits"))
    client.post(f"/tracks/{analysed}/cues", json={"type": "MEMORY", "bar": 0, "beat": 3, "label": "Pickup"})
    client.post(f"/tracks/{analysed}/annotations", json={"bar": 0, "beat": 2, "text": "cut away"})  # 1.0 s
    client.post(f"/tracks/{analysed}/annotations", json={"bar": 1, "beat": 0, "text": "kept"})  # 2.0 s
    # 120 BPM, first beat 0: keep 0-1 s and 1.25-3 s (half a beat removed, off the grid).
    edit = {"sample_rate": 44100, "segments": [{"start": 0, "end": 44100}, {"start": 55125, "end": 132300}]}
    result = client.post(
        f"/tracks/{analysed}/edit/export", json={"edit": edit, "format": "wav", "quality": 16}
    )
    assert result.status_code == 200
    new_id = result.json()["track_id"]

    new = client.get(f"/tracks/{new_id}").json()
    assert new["edited_from"] == analysed and new["title"] == "Jetsetter (Edited)" and new["bpm"] == 120
    assert new["camelot_key"] == client.get(f"/tracks/{analysed}").json()["camelot_key"]
    grid = client.get(f"/tracks/{new_id}/analysis").json()["beatgrid"]
    assert grid["source"] == "USER"
    assert [(a["time"], a["beat"]) for a in grid["anchors"]] == [(0, 1), (1.25, 4)]
    cues = {c["label"]: c for c in client.get(f"/tracks/{new_id}/cues").json()}
    assert (cues["Pickup"]["bar"], cues["Pickup"]["beat"]) == (0, 3)  # 1.5 s -> 1.25 s, still beat 4
    # 1.0 s was cut; 2.0 s is heard at 1.75 s, one beat after the 1.25 s beat 4: bar 2 again.
    notes = client.get(f"/tracks/{new_id}/annotations").json()
    assert [(n["text"], n["bar"], n["beat"]) for n in notes] == [("kept", 1, 0)]
    sections = client.get(f"/tracks/{new_id}/analysis").json()["sections"]
    assert sections and sections[0]["type"] == "INTRO" and sections[0]["source"] == "USER"

    xml = client.post("/export/rekordbox/live").json()
    assert xml["tracks"] >= 2
    root = ET.parse(xml["path"]).getroot()
    edits = root.find(".//NODE[@Name='Edits']")
    assert edits is not None and len(edits.findall("TRACK")) == 1
