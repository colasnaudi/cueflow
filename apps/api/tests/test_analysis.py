import wave

import numpy as np
import pytest
from sqlalchemy import select

from app.audio import rhythm
from app.db import SessionLocal
from app.models import Beatgrid, Track
from app.services import analysis
from app.services.scanner import scan
from tests.conftest import make_mp3

SR = rhythm.SAMPLE_RATE


def write_house_loop(path, bpm=124.0, bars=48, first_beat=0.25):
    """Four-on-the-floor kick + offbeat hats + a louder, brighter hit on every bar start."""
    period = 60 / bpm
    total = first_beat + bars * 4 * period + 1
    t = np.arange(int(SR * 0.12)) / SR
    kick = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 35)
    hat = np.random.default_rng(0).normal(0, 1, len(t)) * np.exp(-t * 120) * 0.25
    audio = np.zeros(int(total * SR))
    for beat in range(bars * 4):
        start = int((first_beat + beat * period) * SR)
        audio[start : start + len(t)] += kick * (1.0 if beat % 4 else 1.4)
        off = int((first_beat + (beat + 0.5) * period) * SR)
        audio[off : off + len(t)] += hat
    audio /= np.abs(audio).max() * 1.1
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes((audio * 32767).astype(np.int16).tobytes())
    return path


def fake_result(**overrides):
    return {
        "bpm": 126.0,
        "first_beat": 0.1,
        "downbeat_offset": 1,
        "beat_count": 400,
        "grid_confidence": 0.95,
        "downbeat_confidence": 0.9,
        "musical_key": "Am",
        "camelot_key": "8A",
        "key_strength": 0.8,
        "energy_curve": [0.5, 1.0],
        "sections": [
            {"type": "INTRO", "start_bar": 0, "end_bar": 16, "confidence": 0.9},
            {"type": "BREAK", "start_bar": 16, "end_bar": 32, "confidence": 0.8},
        ],
        "vocal_curve": [0.1, 0.9],
        "vocal_probability": 0.4,
        "duration": 190.0,
    } | overrides


def test_constant_grid_is_exact_on_a_synthetic_loop(tmp_path):
    import essentia.standard as es

    path = write_house_loop(tmp_path / "loop.wav", bpm=124.0, first_beat=0.25)
    audio = es.MonoLoader(filename=str(path), sampleRate=SR)()
    bpm, first_beat, confidence = rhythm.fit_grid(audio)
    assert bpm == 124.0
    assert abs(first_beat - 0.25) < 0.005
    assert confidence > 0.9


def test_downbeat_phase_votes_on_the_grid():
    period = 60 / 120
    downbeats = 0.3 + period * np.array([2, 6, 10, 14, 18, 23])  # one outlier
    assert rhythm.downbeat_phase(downbeats, 0.3, period) == (2, pytest.approx(5 / 6, abs=1e-3))
    assert rhythm.downbeat_phase(np.array([]), 0.3, period) == (0, 0.0)


def test_vocals_are_averaged_per_bar():
    from app.audio.vocals import per_bar

    timeline = np.array([0.0, 0.2, 1.0, 1.0, 0.5])  # one value per ~1 s
    assert per_bar(timeline, np.array([0.0, 2.0, 4.0, 4.4])) == [0.1, 1.0, 0.5]
    assert per_bar(np.array([]), np.array([0.0, 2.0])) == []


def test_bar_energy_is_relative_to_the_loudest_bar():
    audio = np.concatenate([np.full(SR, 0.1), np.full(SR, 1.0), np.full(SR, 0.001)])
    # 0.1 is 20 dB below the loudest bar: (30 - 20) / 30; 0.001 (-60 dB) is clipped to 0.
    assert rhythm.bar_energy(audio, np.array([0.0, 1.0, 2.0, 3.0])) == [
        pytest.approx(1 / 3, abs=1e-3),
        1.0,
        0.0,
    ]


def one_track(title):
    with SessionLocal() as session:
        return session.scalar(select(Track).where(Track.title == title))


def test_save_fills_only_empty_values_and_shares_with_copies(library):
    import shutil

    shutil.copy(library / "Artist X - Untagged Groove.mp3", library / "copy.mp3")
    scan(library)
    with SessionLocal() as session:
        tagged = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        analysis.save(session, tagged, fake_result(bpm=128.0, camelot_key="1A", musical_key="Abm"))
        untagged = session.scalar(select(Track).where(Track.title == "Untagged Groove"))
        analysis.save(session, untagged, fake_result())
        session.commit()
        session.expunge(untagged)

    jet = one_track("Jetsetter")
    assert (float(jet.bpm), jet.bpm_source, jet.camelot_key, jet.key_source) == (129.0, "TAG", "7A", "TAG")
    with SessionLocal() as session:
        copies = session.scalars(select(Track).where(Track.file_hash == untagged.file_hash)).all()
        assert len(copies) == 2
        for copy in copies:
            assert (float(copy.bpm), copy.bpm_source, copy.camelot_key, copy.status) == (
                126.0,
                "ANALYSIS",
                "8A",
                "ANALYZED",
            )
            assert session.get(Beatgrid, copy.id).downbeat_offset == 1


def test_user_grid_survives_reanalysis_unless_reset(library):
    scan(library)
    with SessionLocal() as session:
        track = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        analysis.save(session, track, fake_result(downbeat_offset=1))
        analysis.shift_downbeat(session, track, -2)
        session.commit()
        assert (session.get(Beatgrid, track.id).downbeat_offset, session.get(Beatgrid, track.id).source) == (
            3,
            "USER",
        )

        analysis.save(session, track, fake_result(downbeat_offset=0, bpm=127.0))
        session.commit()
        grid = session.get(Beatgrid, track.id)
        assert (grid.downbeat_offset, float(grid.bpm), grid.source) == (3, 126.0, "USER")

        analysis.save(session, track, fake_result(downbeat_offset=0), reset_grid=True)
        session.commit()
        assert (session.get(Beatgrid, track.id).downbeat_offset, session.get(Beatgrid, track.id).source) == (
            0,
            "ANALYSIS",
        )


def test_rescan_keeps_user_and_analysed_values(library):
    scan(library)
    with SessionLocal() as session:
        untagged = session.scalar(select(Track).where(Track.title == "Untagged Groove"))
        analysis.save(session, untagged, fake_result())
        jet = session.scalar(select(Track).where(Track.title == "Jetsetter"))
        jet.bpm, jet.bpm_source = 130, "USER"
        session.commit()
    # Force the scanner to re-read both files.
    for path in (library / "Artist X - Untagged Groove.mp3", library / "House" / "a.mp3"):
        path.touch()
    scan(library)
    assert (float(one_track("Untagged Groove").bpm), one_track("Untagged Groove").bpm_source) == (
        126.0,
        "ANALYSIS",
    )
    assert (float(one_track("Jetsetter").bpm), one_track("Jetsetter").bpm_source) == (130.0, "USER")


def test_analysis_api(client, library, monkeypatch):
    scan(library)
    track_id = client.get("/tracks", params={"q": "jetsetter"}).json()["items"][0]["id"]
    assert client.get(f"/tracks/{track_id}/analysis").json()["beatgrid"] is None
    assert client.post(f"/tracks/{track_id}/beatgrid/shift", json={"beats": 1}).status_code == 409

    monkeypatch.setattr(rhythm, "analyse", lambda path: rhythm.RhythmAnalysis(**fake_result(bpm=128.0)))
    body = client.post(f"/tracks/{track_id}/analysis").json()
    assert (body["beatgrid"]["bpm"], body["camelot_key"], len(body["energy_curve"])) == (128.0, "8A", 2)
    assert [(s["type"], s["start_bar"], s["end_bar"], s["source"]) for s in body["sections"]] == [
        ("INTRO", 0, 16, "AUDIO"),
        ("BREAK", 16, 32, "AUDIO"),
    ]
    assert (body["vocal_curve"], body["vocal_probability"]) == ([0.1, 0.9], 0.4)
    # Re-analysing replaces the detected sections instead of piling them up.
    assert len(client.post(f"/tracks/{track_id}/analysis").json()["sections"]) == 2

    body = client.post(f"/tracks/{track_id}/beatgrid/shift", json={"beats": 1}).json()
    assert (body["beatgrid"]["downbeat_offset"], body["beatgrid"]["source"]) == (2, "USER")
    assert client.post(f"/tracks/{track_id}/beatgrid/shift", json={"beats": 9}).status_code == 422

    track = client.post(f"/tracks/{track_id}/analysis/apply", json={"fields": ["bpm", "key"]}).json()
    assert (track["bpm"], track["bpm_source"], track["camelot_key"], track["key_source"]) == (
        128.0,
        "ANALYSIS",
        "8A",
        "ANALYSIS",
    )

    track = client.patch(f"/tracks/{track_id}", json={"bpm": 127.5}).json()
    assert track["bpm_source"] == "USER"


def test_analyse_endpoint_reports_undecodable_files(client, library, monkeypatch):
    scan(library)
    track_id = client.get("/tracks").json()["items"][0]["id"]

    def broken(path):
        raise RuntimeError("cannot decode")

    monkeypatch.setattr(rhythm, "analyse", broken)
    response = client.post(f"/tracks/{track_id}/analysis")
    assert response.status_code == 422 and "cannot decode" in response.json()["detail"]


def test_library_job_end_to_end(library):
    """Real DSP + beat model in a worker process on a synthetic 124 BPM loop."""
    write_house_loop(library / "Loop.wav", bpm=124.0, bars=40)
    make_mp3(library / "short.mp3", seconds=5, freq=700)
    scan(library)

    status = analysis.run(workers=1)
    assert (status.state, status.errors) == ("completed", [])
    assert status.analyzed == 1  # only the loop: the fixture tracks are 3 s long
    loop = one_track("Loop")
    with SessionLocal() as session:
        grid = session.get(Beatgrid, loop.id)
    assert float(grid.bpm) == 124.0
    assert (float(loop.bpm), loop.bpm_source) == (124.0, "ANALYSIS")
    with SessionLocal() as session:
        sections = analysis.sections_of(session, loop.id)
        dsp = analysis.dsp_analysis(session, loop.id)
    # A constant kick from start to end is one groove, and a kick loop has no voice.
    assert [s.type for s in sections] == ["GROOVE"]
    assert len(dsp.vocal_curve) == len(dsp.energy_curve) and float(dsp.vocal_probability) < 0.5
    assert analysis.run(workers=1).total == 0  # nothing left to analyse
