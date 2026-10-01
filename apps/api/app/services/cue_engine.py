"""Rule engine: sections + vocal activity -> hot cues and memory cues (musical positions, CLAUDE.md §16/18).

Hot cues follow the DJ layout of the spec:
  A START · B GROOVE · C BREAK · D DROP · E VOCAL · F SECOND DROP · G OUTRO
A cue is only placed when its section exists, never twice at the same position. Every section start also
gets a memory cue (Rekordbox shows them as structure markers on the waveform).
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass

VOCAL_ON = 0.6  # voice probability...
VOCAL_BARS = 2  # ...held this many bars = a vocal entry

# Rekordbox hot cue palette.
COLORS = {
    "START": "#28E214",
    "INTRO": "#28E214",
    "GROOVE": "#305AFF",
    "BREAK": "#AA72FF",
    "BUILD": "#FFA000",
    "DROP": "#E62828",
    "VOCAL": "#FFD300",
    "OUTRO": "#8C8C8C",
}


@dataclass
class PlannedCue:
    slot: str
    type: str  # HOT | MEMORY
    label: str
    bar: int
    beat: int
    color: str
    confidence: float

    def as_dict(self) -> dict:
        return asdict(self)


def _starts(sections: Sequence, kind: str) -> list:
    return [s for s in sections if s.type == kind]


def _vocal_entry(vocal_curve: Sequence[float], skip_before: int) -> int | None:
    """First bar from `skip_before` where the voice holds for VOCAL_BARS bars."""
    for bar in range(skip_before, len(vocal_curve) - VOCAL_BARS + 1):
        if all(v >= VOCAL_ON for v in vocal_curve[bar : bar + VOCAL_BARS]):
            return bar
    return None


def plan_cues(sections: Sequence, vocal_curve: Sequence[float] = ()) -> list[PlannedCue]:
    """`sections`: objects with type, start_bar, start_beat and confidence (DB rows or structure.Section)."""
    if not sections:
        return []
    groove, breaks, drops, outros = (_starts(sections, k) for k in ("GROOVE", "BREAK", "DROP", "OUTRO"))
    intro_end = next((s.start_bar for s in sections if s.type != "INTRO"), 0)

    candidates: list[tuple[str, str, int, int, float]] = [("A", "START", 0, 0, 0.95)]
    for slot, label, picked in (
        ("B", "GROOVE", groove[:1]),
        ("C", "BREAK", breaks[:1]),
        ("D", "DROP", drops[:1]),
    ):
        candidates += [(slot, label, s.start_bar, s.start_beat, float(s.confidence or 0.5)) for s in picked]
    vocal = _vocal_entry(vocal_curve, intro_end)
    if vocal is not None:
        candidates.append(("E", "VOCAL", vocal, 0, 0.6))
    candidates += [("F", "DROP 2", s.start_bar, s.start_beat, float(s.confidence or 0.5)) for s in drops[1:2]]
    candidates += [("G", "OUTRO", s.start_bar, s.start_beat, float(s.confidence or 0.5)) for s in outros[:1]]

    cues: list[PlannedCue] = []
    taken: set[tuple[int, int]] = set()
    for slot, label, bar, beat, confidence in sorted(candidates):
        if (bar, beat) in taken:
            continue  # never two hot cues on the same beat
        taken.add((bar, beat))
        color = COLORS["DROP" if label.startswith("DROP") else label]
        cues.append(PlannedCue(slot, "HOT", label, bar, beat, color, round(confidence, 3)))

    for index, section in enumerate(sorted(sections, key=lambda s: (s.start_bar, s.start_beat)), start=1):
        cues.append(
            PlannedCue(
                f"M{index:02d}",
                "MEMORY",
                section.type,
                section.start_bar,
                section.start_beat,
                COLORS[section.type],
                round(float(section.confidence or 0.5), 3),
            )
        )
    return cues
