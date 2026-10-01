"""Section detection on per-bar features measured on real house tracks (tests/fixtures/structure/*.json).

Each fixture holds, for every bar, the kick / bass / mid / high levels in dB computed by rhythm.bar_features.
Expected layouts are 1-based bar numbers, as a DJ counts them.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.audio.structure import Section, detect_sections, downbeat_shift

FIXTURES = Path(__file__).parent / "fixtures" / "structure"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def features(name: str) -> np.ndarray:
    return np.array(fixture(name)["features"])


def sections_of(name: str):
    data = fixture(name)
    return detect_sections(
        np.array(data["features"]), np.array(data["beat_features"]), data["first_bar_beat"]
    )


def layout(sections) -> list[tuple]:
    """1-based bar (and beat when not on beat 1), as a DJ counts them."""
    return [(s.type, s.start_bar + 1) + ((s.start_beat + 1,) if s.start_beat else ()) for s in sections]


# (sections, beats to move bar 1 by) — on each track's own grid, before that bar-1 correction.
EXPECTED = {
    # Reported by the user: the second drop is at 2:59.55, bar 96 — not on a 4-bar phrase (12-bar break,
    # 3-bar fake drop at 85-87, 8-bar cut). Snapping to phrases put it on bar 97.
    "broken_hill_wtf_extended_mix": (
        [
            ("INTRO", 1),
            ("GROOVE", 17),
            ("BREAK", 33),
            ("BUILD", 41),
            ("DROP", 49),
            ("BREAK", 72),
            ("BUILD", 85),
            ("DROP", 96),
            ("OUTRO", 132),
        ],
        0,
    ),
    # Bass out from 49, everything cut at 65 then a kick roll on 70-72: the build, not the drop.
    "jetsetter": ([("INTRO", 1), ("GROOVE", 9), ("BREAK", 49), ("BUILD", 65), ("DROP", 73)], 0),
    # Filter opening: kick and bass reach full level two beats into bar 132 here, so bar 1 is 2 beats off.
    "more_love_rampa_me_remix": (
        [("INTRO", 1), ("GROOVE", 25), ("BREAK", 69), ("BUILD", 122), ("DROP", 132, 3), ("OUTRO", 181)],
        2,
    ),
    # Both drops on beat 3 of this grid: the downbeat model was 2 beats off.
    "perplexer_original_mix": (
        [
            ("INTRO", 1),
            ("GROOVE", 49),
            ("BREAK", 79),
            ("DROP", 97, 3),
            ("BREAK", 121),
            ("DROP", 129, 3),
            ("OUTRO", 157),
        ],
        2,
    ),
    # 4-bar kick cuts are fills; the drop comes on the last beat of bar 120 on this grid.
    "don_t_touch_that_dial": (
        [("INTRO", 1), ("GROOVE", 17), ("BREAK", 105), ("DROP", 120, 4), ("OUTRO", 169)],
        3,
    ),
    "shepard_s_tone_x_don_t_stop_the_music_ju": (
        [
            ("INTRO", 1),
            ("GROOVE", 33),
            ("BREAK", 65),
            ("DROP", 81),
            ("BREAK", 113),
            ("BUILD", 122),
            ("DROP", 153),
            ("OUTRO", 200),
        ],
        0,
    ),
    "count_on_you": (
        [
            ("INTRO", 1),
            ("GROOVE", 25),
            ("BREAK", 41),
            ("DROP", 49),
            ("BREAK", 65),
            ("BUILD", 80),
            ("DROP", 89),
            ("BREAK", 105),
            ("DROP", 113),
            ("OUTRO", 129),
        ],
        0,
    ),
    "work": (
        [
            ("INTRO", 1),
            ("GROOVE", 33),
            ("BREAK", 57),
            ("DROP", 73),
            ("BREAK", 97),
            ("DROP", 121),
            ("OUTRO", 144),
        ],
        0,
    ),
    # Drops on different beats (81.1, 137.4): no consistent evidence, bar 1 is left alone.
    "beat_goes": (
        [
            ("INTRO", 1),
            ("GROOVE", 33),
            ("BREAK", 65),
            ("BUILD", 77),
            ("DROP", 81),
            ("BREAK", 105),
            ("BUILD", 132),
            ("DROP", 137, 4),
            ("OUTRO", 165),
        ],
        0,
    ),
    "y_dontchu_the_gang_raw_remix_du_mad": (
        [
            ("INTRO", 1),
            ("GROOVE", 17),
            ("BREAK", 49),
            ("DROP", 65),
            ("BREAK", 97),
            ("BUILD", 105),
            ("DROP", 112, 2),
            ("OUTRO", 177),
        ],
        0,
    ),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_tracks(name):
    sections = sections_of(name)
    assert (layout(sections), downbeat_shift(sections)) == EXPECTED[name]


def test_every_fixture_has_an_expected_layout():
    assert sorted(p.stem for p in FIXTURES.glob("*.json")) == sorted(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sections_tile_the_track(name):
    sections = sections_of(name)
    position = [(s.start_bar * 4 + s.start_beat, s.end_bar * 4 + s.end_beat) for s in sections]
    assert position[0][0] == 0 and sections[-1].end_bar == len(features(name))
    assert all(a[1] == b[0] for a, b in zip(position, position[1:], strict=False))
    assert all(end - start >= 12 for start, end in position)  # >= 3 bars even after beat placement
    assert all(0 < s.confidence <= 1 for s in sections)


def synthetic(*parts: tuple[int, float, float]) -> np.ndarray:
    """Bars of (count, kick dB, bass dB) with flat mids/highs."""
    rows = [[kick, bass, -2.0, -2.0] for count, kick, bass in parts for _ in range(count)]
    return np.array(rows)


def test_fake_drop_belongs_to_the_build():
    """Full groove back for 4 bars after the break, cut again, then the real drop."""
    bands = synthetic((32, 0, 0), (16, -30, -40), (4, 0, 0), (4, -30, -40), (32, 0, 0))
    assert layout(detect_sections(bands)) == [("GROOVE", 1), ("BREAK", 33), ("BUILD", 49), ("DROP", 57)]


def test_kick_without_bass_is_not_a_drop():
    """Kick back at full level without the bassline for 8 bars: the drop waits for the bass."""
    bands = synthetic((32, 0, 0), (16, -30, -40), (8, 0, -25), (32, 0, 0))
    assert layout(detect_sections(bands)) == [("GROOVE", 1), ("BREAK", 33), ("BUILD", 49), ("DROP", 57)]


def test_too_short_tracks_have_no_sections_and_flat_ones_are_one_groove():
    assert detect_sections(np.zeros((8, 4))) == []
    # Levels are relative to the track itself: a track that never changes is one long groove.
    assert layout(detect_sections(synthetic((32, -30, -40)))) == [("GROOVE", 1)]


def test_drop_placed_on_the_beat_where_kick_and_bass_return():
    """Bar-level says bar 49; per beat, kick + bass come back on beat 3 of bar 48 (a 2-beat pickup)."""
    bars = synthetic((32, 0, 0), (16, -30, -40), (32, 0, 0))
    beats = np.repeat(bars, 4, axis=0)
    beats[47 * 4 + 2 : 47 * 4 + 4] = [0, 0, -2, -2]  # beats 3-4 of bar 48 already full
    sections = detect_sections(bars, beats, first_bar_beat=0)
    assert layout(sections) == [("GROOVE", 1), ("BREAK", 33), ("DROP", 48, 3)]
    assert (sections[1].end_bar, sections[1].end_beat) == (47, 2)


def test_downbeat_shift_needs_agreeing_drops():
    def drops(*beats):
        return [Section("DROP", 10 * i, 10 * i + 8, 0.8, start_beat=b) for i, b in enumerate(beats)]

    assert downbeat_shift(drops(2, 2)) == 2
    assert downbeat_shift(drops(3)) == 3
    assert downbeat_shift(drops(0, 3)) == 0  # one drop on the bar line, one off: no evidence
    assert downbeat_shift(drops(2, 2, 0)) == 2
    assert downbeat_shift([]) == 0
