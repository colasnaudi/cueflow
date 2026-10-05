import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None = None
    source: str | None = None


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
    filename: str
    title: str | None
    artist: str | None
    album: str | None
    label: str | None
    genre: str | None
    year: int | None
    duration_ms: int | None
    bpm: float | None
    bpm_source: str | None
    musical_key: str | None
    camelot_key: str | None
    key_source: str | None
    edited_from: uuid.UUID | None = None
    bitrate: int | None
    sample_rate: int | None
    rating: int
    status: str
    file_size: int
    tags: list[TagOut]
    created_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def _flatten_tags(cls, value):
        return [
            {"id": tt.tag.id, "name": tt.tag.name, "category": tt.tag.category, "source": tt.source}
            if hasattr(tt, "tag")
            else tt
            for tt in value
        ]


class TrackPage(BaseModel):
    items: list[TrackOut]
    total: int
    limit: int
    offset: int


class TrackUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=0, le=5)
    genre: str | None = None
    bpm: float | None = Field(default=None, ge=40, le=250)
    musical_key: str | None = None


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class TagCount(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None
    count: int


class Facet(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    genres: list[Facet]
    keys: list[Facet]
    bpm_min: float | None
    bpm_max: float | None
    total: int


class FolderNode(BaseModel):
    name: str
    path: str
    count: int
    children: list["FolderNode"]


class ScanRequest(BaseModel):
    path: str | None = None
    reread: bool = False  # re-read the tags of unchanged files too


SortField = Literal["artist", "title", "bpm", "key", "genre", "rating", "duration", "added"]


class Suggestion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    genre: str
    confidence: float | None
    source: str
    rank: int


class ReviewState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    chosen_genre: str | None
    previous_genre: str | None
    reviewed_at: datetime | None


class ReviewItem(BaseModel):
    track: TrackOut
    folder: str
    suggestions: list[Suggestion]
    review: ReviewState


class ReviewPage(BaseModel):
    items: list[ReviewItem]
    total: int
    counts: dict[str, int]


class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "reset"]
    genre: str | None = Field(default=None, max_length=60)


class BulkApprove(BaseModel):
    track_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class DuplicateCopy(BaseModel):
    track: TrackOut
    folder: str
    protected: bool


class DuplicateGroup(BaseModel):
    keep_ids: list[uuid.UUID]
    copies: list[DuplicateCopy]


class DuplicatePage(BaseModel):
    groups: list[DuplicateGroup]
    total_groups: int
    removable_files: int
    removable_bytes: int


class ResolveDuplicates(BaseModel):
    keep_id: uuid.UUID
    remove_ids: list[uuid.UUID] = Field(min_length=1)


class ShortFolder(BaseModel):
    folder: str
    count: int
    bytes: int
    sample_folder: bool


class ShortTracks(BaseModel):
    folders: list[ShortFolder]
    total: int
    max_ms: int


class DeleteShort(BaseModel):
    max_ms: int = Field(ge=1_000, le=600_000)
    folders: list[str] = Field(min_length=1)


class DeleteTracks(BaseModel):
    track_ids: list[uuid.UUID] = Field(min_length=1)


class TrashResult(BaseModel):
    removed: int
    freed_bytes: int
    errors: list[str]


class Anchor(BaseModel):
    """From `time` on, beats every 60/`bpm` s; the beat at `time` is beat `beat` (1-4) of its bar."""

    time: float = Field(ge=0, le=24 * 3600)
    bpm: float = Field(ge=40, le=250)
    beat: int = Field(ge=1, le=4)


class BeatgridOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bpm: float
    first_beat: float
    downbeat_offset: int
    beats_per_bar: int
    grid_confidence: float | None
    downbeat_confidence: float | None
    source: str
    # Tempo changes; None = constant grid.
    anchors: list[Anchor] | None = None


class BeatgridUpdate(BaseModel):
    anchors: list[Anchor] = Field(min_length=1, max_length=64)

    @field_validator("anchors")
    @classmethod
    def distinct_times(cls, anchors: list[Anchor]) -> list[Anchor]:
        times = sorted(a.time for a in anchors)
        if any(b - a < 0.1 for a, b in zip(times, times[1:], strict=False)):
            raise ValueError("two tempo changes cannot be less than 0.1 s apart")
        return anchors


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    start_bar: int
    end_bar: int
    start_beat: int
    end_beat: int
    confidence: float | None
    source: str
    label: str | None = None
    color: str | None = None


SectionType = Literal[
    "INTRO", "GROOVE", "VERSE", "BUILD", "DROP", "BREAK", "CHORUS", "BRIDGE", "OUTRO", "CUSTOM"
]
Color = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class SectionIn(BaseModel):
    type: SectionType
    label: str | None = Field(default=None, max_length=40)
    color: str | None = Color
    start_bar: int = Field(ge=-64, le=10_000)
    start_beat: int = Field(default=0, ge=0, le=3)
    end_bar: int = Field(ge=-64, le=10_000)
    end_beat: int = Field(default=0, ge=0, le=3)


class SectionsUpdate(BaseModel):
    sections: list[SectionIn] = Field(min_length=1, max_length=200)

    @field_validator("sections")
    @classmethod
    def ordered(cls, sections: list[SectionIn]) -> list[SectionIn]:
        previous_end = None
        for s in sections:
            start, end = s.start_bar * 4 + s.start_beat, s.end_bar * 4 + s.end_beat
            if end <= start:
                raise ValueError("a section must end after it starts")
            if previous_end is not None and start < previous_end:
                raise ValueError("sections must be in order and must not overlap")
            previous_end = end
        return sections


class TrackAnalysis(BaseModel):
    beatgrid: BeatgridOut | None
    musical_key: str | None
    camelot_key: str | None
    key_strength: float | None
    energy_curve: list[float]
    sections: list[SectionOut]
    vocal_curve: list[float]
    vocal_probability: float | None
    analyzed_at: datetime | None


class ApplyAnalysis(BaseModel):
    fields: list[Literal["bpm", "key"]] = Field(min_length=1)


class ShiftDownbeat(BaseModel):
    beats: int = Field(ge=-3, le=3)


class CueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slot: str
    type: str
    label: str | None
    bar: int
    beat: int
    color: str | None
    confidence: float | None
    source: str
    approved: bool
    approved_by: str | None
    loop_beats: float | None = None


class RekordboxExport(BaseModel):
    folder: str | None = None
    approved_only: bool = True
    include_beatgrid: bool = True


class ExportPreview(BaseModel):
    tracks: int
    hot_cues: int
    memory_cues: int
    unapproved_tracks: int


class LiveXml(BaseModel):
    path: str
    exists: bool
    updated_at: datetime | None
    tracks: int | None


class FolderRequest(BaseModel):
    folder: str = Field(min_length=1)


class EditSegment(BaseModel):
    """A slice of the original, in frames at the edit's sample rate, with its gain ramps (fades)."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    # Linear gain ramps multiplied together over the segment: [[gain at start, gain at end], ...] in [0, 1].
    ramps: list[tuple[float, float]] = Field(default_factory=list, max_length=32)

    @field_validator("end")
    @classmethod
    def after_start(cls, end: int, info) -> int:
        if end <= info.data.get("start", 0):
            raise ValueError("a segment must end after it starts")
        return end

    @field_validator("ramps")
    @classmethod
    def unit_gains(cls, ramps: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if any(not 0 <= g <= 1 for ramp in ramps for g in ramp):
            raise ValueError("ramp gains must be between 0 and 1")
        return ramps


class EditList(BaseModel):
    sample_rate: int = Field(gt=0, le=384_000)
    gain_db: float = Field(default=0, ge=-48, le=48)
    segments: list[EditSegment] = Field(min_length=1, max_length=5000)


class TrackEditOut(BaseModel):
    track_id: uuid.UUID
    # The rate the editor decodes the original at: segment frames are counted at this rate.
    sample_rate: int
    edit: EditList | None
    updated_at: datetime | None


class EditExport(BaseModel):
    edit: EditList
    format: Literal["wav", "mp3"]
    # WAV: bit depth (16 | 24). MP3: bitrate in kbps (192 | 256 | 320).
    quality: Literal[16, 24, 192, 256, 320]

    @field_validator("quality")
    @classmethod
    def matches_format(cls, quality: int, info) -> int:
        allowed = {16, 24} if info.data.get("format") == "wav" else {192, 256, 320}
        if quality not in allowed:
            raise ValueError(f"quality must be one of {sorted(allowed)} for this format")
        return quality


class EditExportResult(BaseModel):
    path: str
    filename: str
    duration_ms: int
    # The catalogue track created for the exported file (cues, grid and sections carried over).
    track_id: uuid.UUID


class CueCreate(BaseModel):
    type: Literal["HOT", "MEMORY"]
    bar: int = Field(ge=-64, le=10_000)
    beat: int = Field(default=0, ge=0, le=3)
    label: str | None = Field(default=None, max_length=40)
    color: str | None = Color
    # A loop: its length in beats (1/16 to 512).
    loop_beats: float | None = Field(default=None, ge=0.0625, le=512)
    # Hot cues only: A-H (default: the first free one).
    slot: str | None = Field(default=None, pattern="^[A-H]$")


class CueUpdate(BaseModel):
    bar: int | None = Field(default=None, ge=-64, le=10_000)
    beat: int | None = Field(default=None, ge=0, le=3)
    label: str | None = Field(default=None, max_length=40)
    color: str | None = Color
    loop_beats: float | None = Field(default=None, ge=0.0625, le=512)
    slot: str | None = Field(default=None, pattern="^[A-H]$")


AnnotationKind = Literal["NOTE", "DROP", "VOCAL", "WARNING", "FIRE"]


class AnnotationIn(BaseModel):
    bar: int = Field(ge=-64, le=10_000)
    beat: int = Field(default=0, ge=0, le=3)
    kind: AnnotationKind = "NOTE"
    text: str = Field(default="", max_length=200)


class AnnotationUpdate(BaseModel):
    bar: int | None = Field(default=None, ge=-64, le=10_000)
    beat: int | None = Field(default=None, ge=0, le=3)
    kind: AnnotationKind | None = None
    text: str | None = Field(default=None, max_length=200)


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bar: int
    beat: int
    kind: str
    text: str
