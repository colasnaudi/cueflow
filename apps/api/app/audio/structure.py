"""Rule engine: per-bar features -> DJ sections (INTRO, GROOVE, BREAK, BUILD, DROP, OUTRO).

Input rows are bars; columns are dB levels of the kick (peaks of the < 120 Hz band), the bass (what remains of
that band between the hits), the mids and the highs. Levels are compared with the track's own "full" level
(90th percentile of each column), so mastering loudness does not matter.

How a DJ hears a house arrangement, as rules:
  * a bar is FULL when kick and bass both play near their drop level; KICKLESS when the kick is gone;
  * the body of the track (GROOVE, then DROPs) is made of FULL passages lasting >= 8 bars — a kick that comes
    back for a few bars (fake drop, kick roll, filter opening) is not a drop;
  * between two bodies, a gap of >= 8 bars is a BREAK followed by a BUILD: everything that climbs back
    (kick rolls, fake drops, risers, a filter opening) up to the sustained drop. Shorter gaps are fills;
  * before the first body: INTRO; after the last one: OUTRO (plus a sustained fade at its end).
Boundaries are musical positions (bar indices); the beatgrid turns them into seconds.
"""

from dataclasses import asdict, dataclass

import numpy as np

FULL_KICK_DB = -3.0  # kick within 3 dB of its full level
FULL_BASS_DB = -6.0  # bass within 6 dB (basslines breathe more than kicks)
KICKLESS_DB = -9.0
MIN_BODY_BARS = 8  # a drop lasts; a fake drop does not
MAX_FILL_GAP = 2  # non-full bars tolerated inside a body
MIN_BREAK_GAP = 8  # shorter gaps between bodies are fills
MIN_BREAK_BARS = 4
MAX_BUILD_BARS = 32
BUILD_STEP_DB = 3.0  # level change that starts a build
BUILD_CHANGE_DB = 6.0  # measured: pre-drop cuts and riser entries 8-11 dB, ordinary movement < 5 dB
MIN_BUILD_GAP = 12  # an 8-bar mini-break goes straight back into the drop
PHRASE_BARS = 8
INTRO_MAX_BARS = 32
INTRO_RISE_DB = 2.5
OUTRO_FALL_DB = 3.0
MIN_SECTION_BARS = 4
BEATS_PER_BAR = 4


@dataclass
class Section:
    type: str
    start_bar: int  # 0-based, inclusive
    end_bar: int  # exclusive
    confidence: float
    start_beat: int = 0  # beat inside start_bar (0-3): drops are placed to the beat
    end_beat: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _runs(flags: np.ndarray) -> list[tuple[bool, int, int]]:
    runs, start = [], 0
    for i in range(1, len(flags) + 1):
        if i == len(flags) or flags[i] != flags[start]:
            runs.append((bool(flags[start]), start, i))
            start = i
    return runs


def _bodies(full: np.ndarray) -> list[tuple[int, int]]:
    """FULL passages of >= MIN_BODY_BARS, tolerating gaps of <= MAX_FILL_GAP bars (fills)."""
    bridged = full.copy()
    runs = _runs(full)
    for i, (is_full, start, end) in enumerate(runs):
        if not is_full and end - start <= MAX_FILL_GAP and 0 < i < len(runs) - 1:
            bridged[start:end] = True
    return [(s, e) for is_full, s, e in _runs(bridged) if is_full and e - s >= MIN_BODY_BARS]


def _merge_fills(bodies: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Bodies separated by less than a break (a 4-bar drum cut) are one passage."""
    merged: list[tuple[int, int]] = []
    for start, end in bodies:
        if merged and start - merged[-1][1] < MIN_BREAK_GAP:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _kickless_core(kickless: np.ndarray, start: int, end: int) -> tuple[int, int] | None:
    """First kickless run of >= 4 bars in [start, end), bridging kick hits of <= 2 bars (a hit closing a
    phrase inside a break)."""
    flags = kickless[start:end].copy()
    runs = _runs(flags)
    for i, (is_kickless, s, e) in enumerate(runs):
        if not is_kickless and e - s <= MAX_FILL_GAP and 0 < i < len(runs) - 1:
            flags[s:e] = True
    for is_kickless, s, e in _runs(flags):
        if is_kickless and e - s >= MIN_BREAK_BARS:
            return start + s, start + e
    return None


def _ramp_start(drive: np.ndarray, start: int, end: int) -> int | None:
    """Where a flat passage turns into a climb: the split of drive[start:end] into "flat, then linear ramp"
    with the least squared error, if the ramp sits >= 3 dB above the flat part."""
    best, best_error = None, np.inf
    # Every bar is a candidate: arrangements do not always follow 4-bar phrases.
    for split in range(start + MIN_BREAK_BARS, end - MIN_SECTION_BARS + 1):
        flat, ramp = drive[start:split], drive[split:end]
        x = np.arange(len(ramp))
        slope, intercept = np.polyfit(x, ramp, 1)
        if slope < 0 or ramp.mean() - flat.mean() < BUILD_STEP_DB:
            continue
        error = np.square(flat - flat.mean()).sum() + np.square(ramp - (slope * x + intercept)).sum()
        if error < best_error:
            best, best_error = split, error
    return best


def _merge_variations(bodies: list[tuple[int, int]], kickless: np.ndarray) -> list[tuple[int, int]]:
    """A gap without a kickless core (the bass drops out, the kick keeps going) is a variation of the groove,
    not a break."""
    merged: list[tuple[int, int]] = []
    for start, end in bodies:
        if merged and _kickless_core(kickless, merged[-1][1], start) is None:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _last_change(drive: np.ndarray, start: int, end: int) -> int | None:
    """Biggest level change between the 4 bars before and after a bar (up: a riser kicks in; down: the
    pre-drop cut) in the last 16 bars."""
    best, best_jump = None, BUILD_CHANGE_DB
    for split in range(max(start + MIN_BREAK_BARS, end - 16), end - MIN_SECTION_BARS + 1):
        if split - 4 < start:
            continue
        jump = abs(drive[split : split + 4].mean() - drive[split - 4 : split].mean())
        if jump >= best_jump:
            best, best_jump = split, jump
    return best


def _build_start(drive: np.ndarray, kickless: np.ndarray, full: np.ndarray, start: int, end: int) -> int:
    """First bar of the BUILD in the gap [start, end) between a body and the next drop.

    The BREAK is the flat part; the BUILD is what climbs back to the sustained drop: the kick returning
    without being a drop (fake drop, roll, filter opening) and risers on top of the kickless core.
    """
    core = _kickless_core(kickless, start, end)
    if core is None:
        return start
    # A fake drop (the full groove back for a few bars after the core) is already the build.
    fake = np.flatnonzero(full[core[1] : end])
    build = core[1] + int(fake[0]) if len(fake) else end
    if end - start >= MIN_BUILD_GAP:
        # Short pre-drop builds show as one clear change (a riser enters, or everything cuts before the drop);
        # long progressive ones (filter, Shepard tone) as a ramp.
        change = _last_change(drive, start, end)
        ramp = change if change is not None else _ramp_start(drive, start, end)
        if ramp is not None:
            build = min(build, ramp)
    return (
        int(np.clip(build, start + MIN_BREAK_BARS, end))
        if end - build <= MAX_BUILD_BARS
        else end - MAX_BUILD_BARS
    )


def _intro_end(midhi: np.ndarray, end: int) -> tuple[int, float] | None:
    """End of an intro that already has the kick: the first phrase where mids/highs rise (first 32 bars)."""
    base = midhi[:PHRASE_BARS].mean()
    for bar in range(PHRASE_BARS, min(INTRO_MAX_BARS, end - PHRASE_BARS) + 1, PHRASE_BARS):
        rise = midhi[bar : bar + PHRASE_BARS].mean() - base
        if rise >= INTRO_RISE_DB:
            return bar, float(min(1.0, 0.5 + rise / 10))
    return None


def _outro_start(midhi: np.ndarray, start: int, end: int) -> int | None:
    """Start of a sustained fade at the end of the last body (inside its last 32 bars): every 4-bar block
    from there to the end sits below the body's level."""
    level = np.median(midhi[start:end])
    for bar in range(max(start + PHRASE_BARS, end - 32), end, 4):
        blocks = [midhi[b : min(b + 4, end)].mean() for b in range(bar, end, 4)]
        if all(block <= level - OUTRO_FALL_DB for block in blocks):
            return bar
    return None


def detect_sections(
    features: np.ndarray, beat_features: np.ndarray | None = None, first_bar_beat: int = 0
) -> list[Section]:
    """Sections from per-bar features; with per-beat features (beat k of the grid; bar 0 starts at beat
    `first_bar_beat`), drops are then placed on the exact beat where kick and bass come back."""
    n = len(features)
    if n < 16:
        return []
    relative = features - np.percentile(features, 90, axis=0)
    kick, bass, mid, high = relative.T
    full = (kick >= FULL_KICK_DB) & (bass >= FULL_BASS_DB)
    kickless = kick < KICKLESS_DB
    midhi = (mid + high) / 2
    # What a DJ hears climbing in a build: risers (highs), synths (mids) and the kick coming back.
    drive = (kick + mid + high) / 3

    bodies = _merge_variations(_merge_fills(_bodies(full)), kickless)
    if not bodies:
        return []

    sections: list[Section] = []
    first_start = bodies[0][0]
    if first_start > 0:
        sections.append(Section("INTRO", 0, first_start, 0.8))
    else:
        intro = _intro_end(midhi, bodies[0][1])
        if intro:
            sections.append(Section("INTRO", 0, intro[0], round(intro[1], 2)))

    after_break = False
    for index, (start, end) in enumerate(bodies):
        body_start = sections[-1].end_bar if sections and sections[-1].end_bar > start else start
        share = float(full[start : start + MIN_BODY_BARS].mean())
        body_end = end
        if index == len(bodies) - 1:
            outro = _outro_start(midhi, body_start, end)
            body_end = outro if outro else end
        kind = "DROP" if after_break else ("GROOVE" if index == 0 else sections[-1].type)
        sections.append(Section(kind, body_start, body_end, round(0.5 + 0.4 * share, 2)))
        if body_end < end:
            sections.append(Section("OUTRO", body_end, end, 0.6))

        if index + 1 < len(bodies):
            gap_end = bodies[index + 1][0]
            # A break's start is ambiguous by a bar or two (a fill cuts the bass, the kick fades): between the
            # groove's end and the kickless core, prefer a 4-bar phrase boundary. Drops are never snapped:
            # they sit where kick and bass come back.
            core = _kickless_core(kickless, end, gap_end)
            if core and 0 < core[0] - end <= MAX_FILL_GAP:
                on_phrase = [bar for bar in range(end, core[0] + 1) if bar % 4 == 0]
                sections[-1].end_bar = end = on_phrase[0] if on_phrase else end
            build = _build_start(drive, kickless, full, end, gap_end)
            depth = float(np.clip(-kick[end:build].mean() / 20, 0, 1)) if build > end else 0.0
            sections.append(Section("BREAK", end, build, round(0.5 + 0.5 * depth, 2)))
            rise = float(drive[gap_end - 2 : gap_end].mean() - drive[build : build + 2].mean())
            sections.append(
                Section("BUILD", build, gap_end, round(float(np.clip(0.4 + rise / 30, 0.4, 0.9)), 2))
            )
            after_break = True

    last_end = bodies[-1][1]
    if last_end < n:
        sections.append(Section("OUTRO", last_end, n, 0.7))
    sections = _tidy(sections, n)
    if beat_features is not None and len(beat_features):
        _place_drops_on_beats(sections, beat_features, first_bar_beat)
    return sections


def _place_drops_on_beats(sections: list[Section], beat_features: np.ndarray, first_bar_beat: int) -> None:
    """Move each DROP start to the first beat, within one bar of the bar-level estimate, from which kick and
    bass stay full for 2 bars. Catches drops off the expected bar or beat (pickups, a misplaced bar 1).

    Each beat is compared with the same beat position in the drop's first bars: a rhythmic bassline is
    weaker on some beats of every bar, and that must not read as "not full yet".
    """
    window = 2 * BEATS_PER_BAR
    for i, section in enumerate(sections):
        if section.type != "DROP" or i == 0:
            continue
        estimate = first_bar_beat + BEATS_PER_BAR * section.start_bar + section.start_beat
        reference = beat_features[estimate + BEATS_PER_BAR : estimate + 5 * BEATS_PER_BAR]
        if len(reference) < BEATS_PER_BAR:
            continue
        positions = (
            np.arange(estimate + BEATS_PER_BAR, estimate + BEATS_PER_BAR + len(reference)) % BEATS_PER_BAR
        )
        level = {p: np.median(reference[positions == p], axis=0) for p in range(BEATS_PER_BAR)}

        def is_full(beat: int, level: dict = level) -> bool:
            kick, bass = beat_features[beat, :2] - level[beat % BEATS_PER_BAR][:2]
            return kick >= FULL_KICK_DB and bass >= FULL_BASS_DB

        previous = sections[i - 1]
        previous_start = first_bar_beat + BEATS_PER_BAR * previous.start_bar + previous.start_beat
        for beat in range(max(previous_start + 1, estimate - BEATS_PER_BAR), estimate + BEATS_PER_BAR + 1):
            if beat + window > len(beat_features) or not is_full(beat):
                continue  # the drop beat itself must be full
            if np.mean([is_full(b) for b in range(beat, beat + window)]) >= 7 / 8:
                bar, offset = divmod(beat - first_bar_beat, BEATS_PER_BAR)
                section.start_bar, section.start_beat = bar, offset
                previous.end_bar, previous.end_beat = bar, offset
                break


def downbeat_shift(sections: list[Section]) -> int:
    """Beats to move bar 1 by so that drops start bars, or 0.

    Drops land on a downbeat. When the beat-placed drops of a track agree on another beat of the bar (most of
    them, at least one), the downbeat model picked the wrong beat as bar 1.
    """
    offsets = [s.start_beat for s in sections if s.type == "DROP"]
    if not offsets:
        return 0
    values, counts = np.unique(offsets, return_counts=True)
    best = int(values[np.argmax(counts)])
    return best if best and counts.max() * 2 > len(offsets) else 0


def _tidy(sections: list[Section], n: int) -> list[Section]:
    """Let a neighbour absorb sections shorter than 4 bars, join neighbours of the same type and make the
    sections tile [0, n). Boundaries stay where the music changes: no snapping to 4-bar phrases."""
    tidy: list[Section] = []
    for s in sections:
        start = 0 if not tidy else tidy[-1].end_bar
        end = min(n, s.end_bar)
        if end - start < MIN_SECTION_BARS and end < n:
            continue  # absorbed by the next section
        if tidy and tidy[-1].type == s.type:
            prev = tidy[-1]
            tidy[-1] = Section(s.type, prev.start_bar, end, max(prev.confidence, s.confidence))
        elif end > start:
            tidy.append(Section(s.type, start, end, s.confidence))
    if tidy and tidy[-1].end_bar - tidy[-1].start_bar < MIN_SECTION_BARS and len(tidy) > 1:
        tail = tidy.pop()
        prev = tidy.pop()
        tidy.append(Section(prev.type, prev.start_bar, tail.end_bar, prev.confidence))
    return tidy
