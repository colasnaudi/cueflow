from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Track
from app.schemas import (
    DeleteShort,
    DeleteTracks,
    DuplicateCopy,
    DuplicateGroup,
    DuplicatePage,
    ResolveDuplicates,
    ShortFolder,
    ShortTracks,
    TrackOut,
    TrashResult,
)
from app.services import cleanup

router = APIRouter(prefix="/cleanup", tags=["cleanup"])

MaxMs = Query(default=60_000, ge=1_000, le=600_000)


@router.get("/duplicates", response_model=DuplicatePage)
def duplicates(
    kind: Literal["exact", "probable"] = "exact",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    groups = cleanup.duplicate_groups(session, kind)
    keeps = [cleanup.default_keeps(g) for g in groups]
    removable = [t for group, kept in zip(groups, keeps, strict=True) for t in group if t not in kept]
    page = list(zip(groups, keeps, strict=True))[offset : offset + limit]
    return DuplicatePage(
        groups=[
            DuplicateGroup(
                keep_ids=[t.id for t in kept],
                copies=[
                    DuplicateCopy(
                        track=t,
                        folder=cleanup.relative_folder(t.path),
                        protected=cleanup.is_protected(t.path),
                    )
                    for t in group
                ],
            )
            for group, kept in page
        ],
        total_groups=len(groups),
        removable_files=len(removable),
        removable_bytes=sum(t.file_size for t in removable),
    )


@router.post("/duplicates/resolve", response_model=TrashResult)
def resolve(body: ResolveDuplicates, session: Session = Depends(get_session)):
    try:
        return cleanup.resolve(session, body.keep_id, body.remove_ids)
    except cleanup.CleanupError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/duplicates/resolve-all", response_model=TrashResult)
def resolve_all(session: Session = Depends(get_session)):
    return cleanup.resolve_all_exact(session)


@router.get("/short", response_model=ShortTracks)
def short(max_ms: int = MaxMs, session: Session = Depends(get_session)):
    folders = [ShortFolder(**f) for f in cleanup.short_summary(session, max_ms)]
    return ShortTracks(folders=folders, total=sum(f.count for f in folders), max_ms=max_ms)


@router.get("/short/tracks", response_model=list[TrackOut])
def short_in_folder(folder: str, max_ms: int = MaxMs, session: Session = Depends(get_session)):
    return cleanup.short_tracks(session, max_ms, {folder})


@router.post("/short/delete", response_model=TrashResult)
def delete_short(body: DeleteShort, session: Session = Depends(get_session)):
    return cleanup.trash_tracks(session, cleanup.short_tracks(session, body.max_ms, set(body.folders)))


@router.post("/delete", response_model=TrashResult)
def delete_tracks(body: DeleteTracks, session: Session = Depends(get_session)):
    tracks = list(session.scalars(select(Track).where(Track.id.in_(body.track_ids))))
    return cleanup.trash_tracks(session, tracks)
