"""Section detection on per-bar features measured on real house tracks (tests/fixtures/structure/*.json).

Each fixture holds, for every bar, the kick / bass / mid / high levels in dB computed by rhythm.bar_features.
Expected layouts are 1-based bar numbers, as a DJ counts them.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.audio.structure import detect_sections

FIXTURES = Path(__file__).parent / "fixtures" / "structure"


def features(name: str) -> np.ndarray:
    return np.array(json.loads((FIXTURES / f"{name}.json").read_text())["features"])


def layout(bands: np.ndarray) -> list[tuple[str, int]]:
    return [(s.type, s.start_bar + 1) for s in detect_sections(bands)]


EXPECTED = {
    # Bass out from 49, everything cut at 65 then a kick roll on 70-72: the build, not the drop.
    "jetsetter": [("INTRO", 1), ("GROOVE", 9), ("BREAK", 49), ("BUILD", 65), ("DROP", 73)],
    # Filter opening: kick and bass climb from 121 and only reach full level at 133.
    "more_love_rampa_me_remix": [
        ("INTRO", 1),
        ("GROOVE", 25),
        ("BREAK", 69),
        ("BUILD", 121),
        ("DROP", 133),
        ("OUTRO", 181),
    ],
    # Shepard-tone riser over a kickless 40 bars: break, then a long build.
    "shepard_s_tone_x_don_t_stop_the_music_ju": [
        ("INTRO", 1),
        ("GROOVE", 33),
        ("BREAK", 65),
        ("DROP", 81),
        ("BREAK", 113),
        ("BUILD", 121),
        ("DROP", 153),
        ("OUTRO", 201),
    ],
    # Kickless intro and 8-bar mini-breaks; mids/highs climb from 73 to the drop at 89.
    "count_on_you": [
        ("INTRO", 1),
        ("GROOVE", 25),
        ("BREAK", 41),
        ("DROP", 49),
        ("BREAK", 65),
        ("BUILD", 73),
        ("DROP", 89),
        ("BREAK", 105),
        ("DROP", 113),
        ("OUTRO", 129),
    ],
    # 4-bar kick cuts are fills; a kick hit on bar 112 does not split the break.
    "don_t_touch_that_dial": [("INTRO", 1), ("GROOVE", 17), ("BREAK", 105), ("DROP", 121), ("OUTRO", 169)],
    # Fading breaks straight back into the drop: no build.
    "perplexer_original_mix": [
        ("INTRO", 1),
        ("GROOVE", 49),
        ("BREAK", 81),
        ("DROP", 97),
        ("BREAK", 121),
        ("DROP", 129),
        ("OUTRO", 157),
    ],
    "work": [
        ("INTRO", 1),
        ("GROOVE", 33),
        ("BREAK", 57),
        ("DROP", 73),
        ("BREAK", 97),
        ("DROP", 121),
        ("OUTRO", 145),
    ],
    "beat_goes": [
        ("INTRO", 1),
        ("GROOVE", 33),
        ("BREAK", 65),
        ("DROP", 81),
        ("BREAK", 105),
        ("BUILD", 133),
        ("DROP", 137),
        ("OUTRO", 165),
    ],
    # Bass-less bars then a pre-drop cut (105-111) and one full bar: build, drop at 113.
    "y_dontchu_the_gang_raw_remix_du_mad": [
        ("INTRO", 1),
        ("GROOVE", 17),
        ("BREAK", 49),
        ("DROP", 65),
        ("BREAK", 97),
        ("BUILD", 105),
        ("DROP", 113),
        ("OUTRO", 177),
    ],
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_tracks(name):
    assert layout(features(name)) == EXPECTED[name]


def test_every_fixture_has_an_expected_layout():
    assert sorted(p.stem for p in FIXTURES.glob("*.json")) == sorted(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sections_tile_the_track(name):
    bands = features(name)
    sections = detect_sections(bands)
    assert sections[0].start_bar == 0 and sections[-1].end_bar == len(bands)
    assert all(a.end_bar == b.start_bar for a, b in zip(sections, sections[1:], strict=False))
    assert all(0 < s.confidence <= 1 for s in sections)
    assert all(s.end_bar - s.start_bar >= 4 for s in sections)


def synthetic(*parts: tuple[int, float, float]) -> np.ndarray:
    """Bars of (count, kick dB, bass dB) with flat mids/highs."""
    rows = [[kick, bass, -2.0, -2.0] for count, kick, bass in parts for _ in range(count)]
    return np.array(rows)


def test_fake_drop_belongs_to_the_build():
    """Full groove back for 4 bars after the break, cut again, then the real drop."""
    bands = synthetic((32, 0, 0), (16, -30, -40), (4, 0, 0), (4, -30, -40), (32, 0, 0))
    assert layout(bands) == [("GROOVE", 1), ("BREAK", 33), ("BUILD", 49), ("DROP", 57)]


def test_kick_without_bass_is_not_a_drop():
    """Kick back at full level without the bassline for 8 bars: the drop waits for the bass."""
    bands = synthetic((32, 0, 0), (16, -30, -40), (8, 0, -25), (32, 0, 0))
    assert layout(bands) == [("GROOVE", 1), ("BREAK", 33), ("BUILD", 49), ("DROP", 57)]


def test_too_short_tracks_have_no_sections_and_flat_ones_are_one_groove():
    assert detect_sections(np.zeros((8, 4))) == []
    # Levels are relative to the track itself: a track that never changes is one long groove.
    assert layout(synthetic((32, -30, -40))) == [("GROOVE", 1)]
