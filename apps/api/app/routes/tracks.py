import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import Integer, and_, cast, func, select, true
from sqlalchemy.orm import Session

from app.audio.keys import normalize_key
from app.db import get_session
from app.models import Tag, Track, TrackTag
from app.schemas import SortField, TagCreate, TrackOut, TrackPage, TrackUpdate
from app.services import media
from app.services.queries import dedupe_filter, folder_filter

router = APIRouter(prefix="/tracks", tags=["tracks"])

# Must match the expression of the ix_tracks_search trigram index (migration 0001).
SEARCH_TEXT = (
    func.coalesce(Track.artist, "")
    + " "
    + func.coalesce(Track.title, "")
    + " "
    + func.coalesce(Track.album, "")
    + " "
    + func.coalesce(Track.label, "")
    + " "
    + Track.filename
)

SORT_COLUMNS = {
    "artist": (func.lower(Track.artist), func.lower(Track.title)),
    "title": (func.lower(Track.title),),
    "bpm": (Track.bpm,),
    "key": (cast(func.rtrim(Track.camelot_key, "AB"), Integer), Track.camelot_key),
    "genre": (func.lower(Track.genre),),
    "rating": (Track.rating,),
    "duration": (Track.duration_ms,),
    "added": (Track.created_at,),
}


def normalize_tag_name(name: str) -> str:
    return "_".join(name.strip().lstrip("#").upper().split())


def get_track(session: Session, track_id: uuid.UUID) -> Track:
    track = session.get(Track, track_id)
    if track is None:
        raise HTTPException(404, "Track not found")
    return track


@router.get("", response_model=TrackPage)
def list_tracks(
    q: str | None = None,
    genre: list[str] = Query(default=[]),
    key: list[str] = Query(default=[], description="Camelot keys, e.g. 8A"),
    tag: list[str] = Query(default=[], description="All given tags must be present"),
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    rating_min: int | None = Query(default=None, ge=0, le=5),
    min_duration_ms: int | None = None,
    dedupe: bool = Query(default=False, description="Show one copy per identical file (same SHA256)"),
    folder: str | None = Query(
        default=None, description="Folder relative to MUSIC_ROOT, subfolders included"
    ),
    sort: SortField = "artist",
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    filters = []
    for word in (q or "").split():
        filters.append(SEARCH_TEXT.ilike(f"%{word}%"))
    if genre:
        filters.append(func.lower(Track.genre).in_([g.lower() for g in genre]))
    if key:
        filters.append(Track.camelot_key.in_([k.upper() for k in key]))
    if bpm_min is not None:
        filters.append(Track.bpm >= bpm_min)
    if bpm_max is not None:
        filters.append(Track.bpm <= bpm_max)
    if rating_min:
        filters.append(Track.rating >= rating_min)
    if min_duration_ms:
        filters.append(Track.duration_ms >= min_duration_ms)
    if dedupe:
        filters.append(dedupe_filter(folder))
    if folder:
        filters.append(folder_filter(folder))
    for name in tag:
        filters.append(
            Track.id.in_(select(TrackTag.track_id).join(Tag).where(Tag.name == normalize_tag_name(name)))
        )

    where = and_(true(), *filters)
    total = session.scalar(select(func.count()).select_from(Track).where(where)) or 0
    columns = SORT_COLUMNS[sort]
    ordering = [c.desc().nulls_last() if order == "desc" else c.asc().nulls_last() for c in columns]
    items = session.scalars(
        select(Track).where(where).order_by(*ordering, Track.id).limit(limit).offset(offset)
    ).all()
    return TrackPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{track_id}", response_model=TrackOut)
def read_track(track_id: uuid.UUID, session: Session = Depends(get_session)):
    return get_track(session, track_id)


@router.patch("/{track_id}", response_model=TrackOut)
def update_track(track_id: uuid.UUID, body: TrackUpdate, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    changes = body.model_dump(exclude_unset=True)
    if "musical_key" in changes:
        musical, camelot = normalize_key(changes.pop("musical_key"))
        if body.musical_key and camelot is None:
            raise HTTPException(422, f"Unknown key: {body.musical_key}")
        track.musical_key, track.camelot_key = musical, camelot
        track.key_source = "USER" if camelot else None
    if "bpm" in changes:
        track.bpm_source = "USER" if changes["bpm"] is not None else None
    for field, value in changes.items():
        setattr(track, field, value)
    session.commit()
    session.refresh(track)
    return track


@router.get("/{track_id}/audio")
def stream_audio(track_id: uuid.UUID, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    path, media_type = media.playable_file(track)
    return FileResponse(path, media_type=media_type)


@router.get("/{track_id}/peaks")
def waveform_peaks(track_id: uuid.UUID, session: Session = Depends(get_session)):
    return media.peaks(get_track(session, track_id))


@router.post("/{track_id}/tags", response_model=TrackOut)
def add_tag(track_id: uuid.UUID, body: TagCreate, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    name = normalize_tag_name(body.name)
    if not name:
        raise HTTPException(422, "Empty tag")
    tag = session.scalar(select(Tag).where(Tag.name == name))
    if tag is None:
        tag = Tag(name=name)
        session.add(tag)
        session.flush()
    if not any(tt.tag_id == tag.id for tt in track.tags):
        track.tags.append(TrackTag(tag=tag, source="USER", confidence=1))
    session.commit()
    session.refresh(track)
    return track


@router.delete("/{track_id}/tags/{tag_id}", response_model=TrackOut)
def remove_tag(track_id: uuid.UUID, tag_id: uuid.UUID, session: Session = Depends(get_session)):
    track = get_track(session, track_id)
    track.tags = [tt for tt in track.tags if tt.tag_id != tag_id]
    session.commit()
    session.refresh(track)
    return track
