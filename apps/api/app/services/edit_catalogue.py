"""An exported edit joins the catalogue: its beatgrid, cues, loops, sections and notes are carried over from
the original through the edit list, so it is ready for the Rekordbox XML without a new analysis."""

from dataclasses import dataclass
from math import ceil
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Annotation, Beatgrid, Cue, Section, Track
from app.schemas import EditList
from app.services import annotations, cues
from app.services.analysis import sections_of
from app.services.scanner import _inspect
from app.services.tempo import BEATS_PER_BAR, Anchor, TempoMap, store


@dataclass(frozen=True)
class Piece:
    """A segment of the edit, in seconds: original [start, end) heard at `at` in the edited file."""

    start: float
    end: float
    at: float


def pieces(edit: EditList) -> list[Piece]:
    result, at = [], 0.0
    for segment in edit.segments:
        start, end = segment.start / edit.sample_rate, segment.end / edit.sample_rate
        result.append(Piece(start, end, at))
        at += end - start
    return result


def map_time(parts: list[Piece], time: float) -> float | None:
    """Where an original moment is first heard in the edit; None when it was cut."""
    return next((p.at + time - p.start for p in parts if p.start <= time < p.end), None)


def map_forward(parts: list[Piece], time: float) -> float | None:
    """Like map_time, but a cut moment moves to the next original material that is heard."""
    mapped = map_time(parts, time)
    if mapped is not None:
        return mapped
    later = [p for p in parts if p.start > time]
    return min(later, key=lambda p: p.start).at if later else None


def carry_grid(original: TempoMap, parts: list[Piece]) -> list[Anchor]:
    """The edited file's tempo map: per piece, the original anchors inside it plus one on its first beat.
    Anchors that continue the previous grid exactly (a cut on the grid) are dropped."""
    candidates: list[Anchor] = []
    for part in parts:
        index = ceil(original.index_of(part.start) - 1e-6)
        times = [original.time_of_index(index)] + [
            a.time for a in original.anchors if part.start < a.time < part.end
        ]
        for time in sorted(t for t in times if t < part.end):
            beat = round(original.index_of(time)) % BEATS_PER_BAR + 1
            candidates.append(Anchor(part.at + time - part.start, original.bpm_at(time), beat))
    kept: list[Anchor] = []
    for anchor in candidates:
        if kept and kept[-1].bpm == anchor.bpm:
            index = TempoMap(kept).index_of(anchor.time)
            on_grid = abs(index - round(index)) * anchor.period < 0.001
            if on_grid and round(index) % BEATS_PER_BAR + 1 == anchor.beat:
                continue
        kept.append(anchor)
    return kept


def _carry_sections(
    session: Session, source: Track, new: Track, old: TempoMap, grid: TempoMap, parts
) -> None:
    starts = []
    for section in sections_of(session, source.id):
        at = map_forward(parts, old.time_of(section.start_bar, section.start_beat))
        if at is not None:
            starts.append((grid.position_of(at), section))
    starts.sort(key=lambda item: item[0])
    duration = parts[-1].at + parts[-1].end - parts[-1].start if parts else 0
    end_of_track = grid.position_of(duration)
    for i, ((bar, beat), section) in enumerate(starts):
        end_bar, end_beat = starts[i + 1][0] if i + 1 < len(starts) else end_of_track
        if end_bar * BEATS_PER_BAR + end_beat <= bar * BEATS_PER_BAR + beat:
            continue
        session.add(
            Section(
                track_id=new.id, type=section.type, label=section.label, color=section.color, source="USER",
                start_bar=bar, start_beat=beat, end_bar=end_bar, end_beat=end_beat,
            )
        )  # fmt: skip


def register(session: Session, source: Track, path: Path, edit: EditList) -> Track:
    """Create the catalogue track of an exported edit and carry the DJ's preparation over."""
    new = Track(**_inspect(path))
    new.edited_from = source.id
    new.genre, new.label, new.year = source.genre, source.label, source.year
    new.rating, new.rating_source = source.rating, source.rating_source
    new.musical_key, new.camelot_key, new.key_source = (
        source.musical_key,
        source.camelot_key,
        source.key_source,
    )
    session.add(new)
    session.flush()

    grid = session.get(Beatgrid, source.id)
    if grid is None:
        return new
    parts = pieces(edit)
    old = TempoMap.of(grid)
    anchors = carry_grid(old, parts)
    if not anchors:
        return new
    carried = Beatgrid(track_id=new.id, source="USER")
    store(carried, anchors)
    session.add(carried)
    new.bpm, new.bpm_source = round(carried.bpm, 2), "USER"
    tempo = TempoMap(anchors)

    for cue in cues.cues_of(session, source.id):
        at = map_time(parts, old.time_of(cue.bar, cue.beat))
        if at is None:
            continue
        bar, beat = tempo.position_of(at)
        session.add(
            Cue(
                track_id=new.id, slot=cue.slot, type=cue.type, label=cue.label, color=cue.color, bar=bar,
                beat=beat, loop_beats=cue.loop_beats, source="USER", approved=True, approved_by="USER",
            )
        )  # fmt: skip
    for note in annotations.of(session, source.id):
        at = map_time(parts, old.time_of(note.bar, note.beat))
        if at is not None:
            bar, beat = tempo.position_of(at)
            session.add(Annotation(track_id=new.id, bar=bar, beat=beat, kind=note.kind, text=note.text))
    _carry_sections(session, source, new, old, tempo, parts)
    return new
