"""Tempo map: musical positions (bar, beat) <-> seconds, for constant and variable beatgrids.

A grid is a list of anchors, the shape of Rekordbox's TEMPO entries: from `time` on, beats come every
60/`bpm` seconds and the beat at `time` is beat `beat` (1-4) of its bar. A constant grid is a single anchor.
Bar 0 starts on the first downbeat at or after the first anchor (CLAUDE.md §16); beats before it belong to
bars -1, -2...
Mirrored by apps/web/lib/tempo.ts.
"""

from dataclasses import dataclass
from math import floor

from app.models import Beatgrid

BEATS_PER_BAR = 4


@dataclass(frozen=True)
class Anchor:
    time: float
    bpm: float
    beat: int  # 1-4: position in its bar of the beat at `time` (Rekordbox Battito)

    @property
    def period(self) -> float:
        return 60 / self.bpm

    def as_dict(self) -> dict:
        return {"time": round(self.time, 4), "bpm": round(self.bpm, 4), "beat": self.beat}


def anchors_of(grid: Beatgrid) -> list[Anchor]:
    if grid.anchors:
        return [Anchor(float(a["time"]), float(a["bpm"]), int(a["beat"])) for a in grid.anchors]
    # Constant grid: the first detected beat is (4 - downbeat_offset) % 4 beats after a downbeat.
    beat = (BEATS_PER_BAR - grid.downbeat_offset) % BEATS_PER_BAR + 1
    return [Anchor(float(grid.first_beat), float(grid.bpm), beat)]


def store(grid: Beatgrid, anchors: list[Anchor]) -> None:
    """Write `anchors` into `grid`: one anchor stays a constant grid (the columns every consumer reads)."""
    anchors = sorted(anchors, key=lambda a: a.time)
    first = anchors[0]
    grid.bpm, grid.first_beat = round(first.bpm, 3), round(first.time, 4)
    grid.downbeat_offset = (BEATS_PER_BAR + 1 - first.beat) % BEATS_PER_BAR
    grid.beats_per_bar = BEATS_PER_BAR
    grid.anchors = [a.as_dict() for a in anchors] if len(anchors) > 1 else None


class TempoMap:
    def __init__(self, anchors: list[Anchor]):
        if not anchors:
            raise ValueError("a tempo map needs at least one anchor")
        self.anchors = sorted(anchors, key=lambda a: a.time)
        # Global beat index of each anchor's beat; index 0 = the downbeat starting bar 0.
        first = self.anchors[0]
        self._starts = [-((BEATS_PER_BAR + 1 - first.beat) % BEATS_PER_BAR)]
        for previous, anchor in zip(self.anchors, self.anchors[1:], strict=False):
            start = self._starts[-1] + round((anchor.time - previous.time) / previous.period)
            # The anchor's own Battito decides the bar phase from here on (a cut or a moved bar 1).
            start += (anchor.beat - 1 - start) % BEATS_PER_BAR
            self._starts.append(start)

    @classmethod
    def of(cls, grid: Beatgrid) -> "TempoMap":
        return cls(anchors_of(grid))

    def _segment_for_index(self, index: float) -> int:
        return max((i for i, start in enumerate(self._starts) if index >= start), default=0)

    def _segment_for_time(self, time: float) -> int:
        return max((i for i, anchor in enumerate(self.anchors) if time >= anchor.time), default=0)

    def time_of_index(self, index: float) -> float:
        """Seconds of a (fractional) global beat index."""
        segment = self._segment_for_index(index)
        anchor = self.anchors[segment]
        return anchor.time + (index - self._starts[segment]) * anchor.period

    def index_of(self, time: float) -> float:
        """(Fractional) global beat index at `time`."""
        segment = self._segment_for_time(time)
        anchor = self.anchors[segment]
        return self._starts[segment] + (time - anchor.time) / anchor.period

    def time_of(self, bar: int, beat: float = 0) -> float:
        return self.time_of_index(bar * BEATS_PER_BAR + beat)

    def position_of(self, time: float) -> tuple[int, int]:
        """Nearest beat to `time`, as (bar, beat 0-3)."""
        index = round(self.index_of(time))
        return floor(index / BEATS_PER_BAR), index % BEATS_PER_BAR

    def bpm_at(self, time: float) -> float:
        return self.anchors[self._segment_for_time(time)].bpm
