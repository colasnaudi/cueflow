from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, cast, func, select, true
from sqlalchemy.orm import Session

from app.config import music_root
from app.db import get_session
from app.models import Tag, Track, TrackTag
from app.schemas import Facet, Facets, FolderNode, FolderRequest, ScanRequest, TagCount
from app.services import scanner
from app.services.folders import build_tree

router = APIRouter(tags=["library"])


@router.post("/library/scan", status_code=202)
def start_scan(body: ScanRequest | None = None):
    try:
        root = scanner.resolve_scan_root(body.path if body else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        scanner.start_in_background(root, reread=bool(body and body.reread))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"root": str(root)}


@router.get("/library/scan")
def scan_status():
    return scanner.status.as_dict()


@router.get("/library/folders", response_model=list[FolderNode])
def folders(
    min_duration_ms: int | None = None, dedupe: bool = False, session: Session = Depends(get_session)
):
    filters = [Track.duration_ms >= min_duration_ms] if min_duration_ms else []
    rows = session.execute(select(Track.path, Track.file_hash).where(true(), *filters)).all()
    # With dedupe, a folder counts distinct files: the same number a click on it shows.
    return build_tree([(path, file_hash if dedupe else None) for path, file_hash in rows], music_root())


@router.get("/library/facets", response_model=Facets)
def facets(min_duration_ms: int | None = None, session: Session = Depends(get_session)):
    base = Track.duration_ms >= min_duration_ms if min_duration_ms else True
    genres = session.execute(
        select(Track.genre, func.count())
        .where(base, Track.genre.is_not(None))
        .group_by(Track.genre)
        .order_by(func.count().desc())
        .limit(40)
    ).all()
    keys = session.execute(
        select(Track.camelot_key, func.count())
        .where(base, Track.camelot_key.is_not(None))
        .group_by(Track.camelot_key)
        .order_by(cast(func.rtrim(Track.camelot_key, "AB"), Integer), Track.camelot_key)
    ).all()
    bpm_min, bpm_max, total = session.execute(
        select(func.min(Track.bpm), func.max(Track.bpm), func.count()).where(base)
    ).one()
    return Facets(
        genres=[Facet(value=g, count=c) for g, c in genres],
        keys=[Facet(value=k, count=c) for k, c in keys],
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        total=total,
    )


@router.get("/tags", response_model=list[TagCount])
def list_tags(session: Session = Depends(get_session)):
    rows = session.execute(
        select(Tag, func.count(TrackTag.track_id))
        .outerjoin(TrackTag)
        .group_by(Tag.id)
        .order_by(func.count(TrackTag.track_id).desc(), Tag.name)
    ).all()
    return [TagCount(id=t.id, name=t.name, category=t.category, count=c) for t, c in rows]


@router.post("/library/reveal", status_code=204)
def reveal(body: FolderRequest):
    """Open a library folder in the Finder (macOS). Only folders inside MUSIC_ROOT."""
    import subprocess
    import sys

    root = music_root()
    target = (root / body.folder.strip("/")).resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        raise HTTPException(422, "Not a folder of the library")
    if sys.platform != "darwin":
        raise HTTPException(501, "Revealing folders is only supported on macOS")
    subprocess.run(["open", str(target)], check=False, timeout=10)
