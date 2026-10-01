"""Rule engine: per-bar band levels -> DJ sections (INTRO, GROOVE, BREAK, BUILD, DROP, OUTRO).

Input rows are bars, columns the low (< 150 Hz: kick + bass), mid (150 Hz - 2 kHz) and high (> 2 kHz) band
levels in dB relative to the track's loudest bar of each band. House arrangements are driven by the kick:
  * no kick for >= 8 bars .......... BREAK (shorter drops are fills and stay in their section)
  * the break's rising last bars .... BUILD
  * the kick back after a break ..... DROP; the kick before the first break is GROOVE
  * the start before the groove ..... INTRO; a fading end ............ OUTRO
Boundaries are musical positions (bar indices), resolved to seconds with the beatgrid.
"""

from dataclasses import asdict, dataclass

import numpy as np

KICK_DB = -9.0  # low band this far below its loudest bar = no kick
MIN_BREAK_BARS = 8
MAX_BREAK_HITS = 2  # kick bars tolerated inside a break
PHRASE_BARS = 8
INTRO_MAX_BARS = 32
INTRO_RISE_DB = 2.5  # mid/high rise marking the end of a kick-only DJ intro
BUILD_RISE_DB = 6.0  # low band climbing back inside a break
OUTRO_FALL_DB = 3.0
MIN_SECTION_BARS = 4  # a last bar of silence is not an OUTRO


@dataclass
class Section:
    type: str
    start_bar: int  # 0-based, inclusive
    end_bar: int  # exclusive
    confidence: float

    def as_dict(self) -> dict:
        return asdict(self)


def _runs(flags: np.ndarray) -> list[tuple[bool, int, int]]:
    runs, start = [], 0
    for i in range(1, len(flags) + 1):
        if i == len(flags) or flags[i] != flags[start]:
            runs.append((bool(flags[start]), start, i))
            start = i
    return runs


def _kick_mask(low: np.ndarray) -> np.ndarray:
    """Kick presence per bar.

    One or two kick bars inside a break (a hit closing a phrase) belong to the break; kickless runs shorter
    than a break are fills, not arrangement changes.
    """
    kick = low > KICK_DB
    runs = _runs(kick)
    for i, (has_kick, start, end) in enumerate(runs):
        if has_kick and end - start <= MAX_BREAK_HITS and 0 < i < len(runs) - 1:
            kick[start:end] = False
    for has_kick, start, end in _runs(kick):
        if not has_kick and end - start < MIN_BREAK_BARS and start > 0 and end < len(kick):
            kick[start:end] = True
    return kick


def _snap(bar: int, n: int, step: int = 4) -> int:
    return int(min(n, max(0, round(bar / step) * step)))


def _intro_end(midhi: np.ndarray, end: int) -> tuple[int, float] | None:
    """End of a kick-only intro: the first phrase where mids/highs rise, within the first 32 bars."""
    base = midhi[:PHRASE_BARS].mean()
    for bar in range(PHRASE_BARS, min(INTRO_MAX_BARS, end - PHRASE_BARS) + 1, PHRASE_BARS):
        rise = midhi[bar : bar + PHRASE_BARS].mean() - base
        if rise >= INTRO_RISE_DB:
            return bar, float(min(1.0, 0.5 + rise / 10))
    return None


def _split_build(low: np.ndarray, midhi: np.ndarray, start: int, end: int) -> int | None:
    """First bar of a BUILD at the end of a break, if the low band or mids/highs climb back."""
    if end - start < 12:
        return None
    first_half = slice(start, start + (end - start) // 2)
    for length in (8, 4):
        tail = slice(end - length, end)
        if (
            low[tail].mean() - low[first_half].mean() >= BUILD_RISE_DB
            or midhi[tail].mean() - midhi[first_half].mean() >= INTRO_RISE_DB
        ):
            return end - length
    return None


def _outro_start(midhi: np.ndarray, start: int, end: int) -> int | None:
    """Start of a sustained fade at the end of the last kick section (only inside the last 32 bars).

    Every 4-bar block from there to the end must sit below the section's level: a mean would let the final
    silent bars drag the outro 30 bars too early.
    """
    level = np.median(midhi[start:end])
    for bar in range(max(start + PHRASE_BARS, end - 32), end, 4):
        blocks = [midhi[b : min(b + 4, end)].mean() for b in range(bar, end, 4)]
        if all(block <= level - OUTRO_FALL_DB for block in blocks):
            return bar
    return None


def detect_sections(bands: np.ndarray) -> list[Section]:
    n = len(bands)
    if n < 16:
        return []
    low, midhi = bands[:, 0], bands[:, 1:].mean(axis=1)
    kick_level = np.median(low[low > KICK_DB]) if np.any(low > KICK_DB) else 0.0
    sections: list[Section] = []
    runs = _runs(_kick_mask(low))
    last_kick_run = max(i for i, run in enumerate(runs) if run[0]) if any(r[0] for r in runs) else -1
    seen_break = False

    for index, (has_kick, start, end) in enumerate(runs):
        last = index == len(runs) - 1
        if not has_kick:
            depth = float(min(1.0, (kick_level - low[start:end].mean()) / 20))
            if start == 0:
                sections.append(Section("INTRO", start, end, round(0.6 + 0.4 * depth, 2)))
            elif last:
                sections.append(Section("OUTRO", start, end, round(0.5 + 0.4 * depth, 2)))
            else:
                seen_break = True
                build = _split_build(low, midhi, start, end)
                sections.append(Section("BREAK", start, build or end, round(0.5 + 0.5 * depth, 2)))
                if build:
                    sections.append(Section("BUILD", build, end, 0.6))
            continue

        body_start = start
        if start == 0:
            intro = _intro_end(midhi, end)
            if intro:
                sections.append(Section("INTRO", 0, intro[0], round(intro[1], 2)))
                body_start = intro[0]
        body_end = end
        if index == last_kick_run:  # the fade can precede a final kickless tail
            outro = _outro_start(midhi, body_start, end)
            if outro:
                body_end = outro
        kind = "DROP" if seen_break else "GROOVE"
        sections.append(Section(kind, body_start, body_end, 0.8 if seen_break else 0.7))
        if body_end < end:
            sections.append(Section("OUTRO", body_end, end, 0.6))

    return _merge(sections, n)


def _merge(sections: list[Section], n: int) -> list[Section]:
    """Snap boundaries to 4-bar phrases, let a neighbour absorb sections shorter than 4 bars and join
    neighbours of the same type."""
    sections = [
        s
        for i, s in enumerate(sections)
        if i == 0 or s.end_bar - s.start_bar >= MIN_SECTION_BARS or s.start_bar == 0
    ]
    if sections:
        sections[-1] = Section(sections[-1].type, sections[-1].start_bar, n, sections[-1].confidence)
    snapped: list[Section] = []
    for s in sections:
        start = _snap(s.start_bar, n) if s.start_bar else 0
        end = n if s.end_bar == n else _snap(s.end_bar, n)
        if snapped:
            start = snapped[-1].end_bar
        if end <= start:
            continue
        if snapped and snapped[-1].type == s.type:
            prev = snapped[-1]
            snapped[-1] = Section(s.type, prev.start_bar, end, max(prev.confidence, s.confidence))
        else:
            snapped.append(Section(s.type, start, end, s.confidence))
    return snapped
