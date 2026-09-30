"""Duplicate detection and removal of unwanted files. Files go to the macOS Trash, never hard-deleted."""

import re
import unicodedata
from collections import defaultdict
from pathlib import Path, PurePath

from send2trash import send2trash
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import music_root
from app.models import Track, TrackTag
from app.services.folders import is_sample_folder

ORGANISED_FOLDER = re.compile(r"^\d+[_ -]")  # 01_NEW_MUSIC, 02_GENRES, ...
# Libraries managed by other apps (Apple Music / iTunes): trashing their files would break those apps.
PROTECTED_FOLDERS = {"media.localized", "itunes media", "itunes"}
LOSSLESS = {".wav", ".aiff", ".aif", ".flac"}
PROBABLE_DURATION_TOLERANCE_MS = 2_000


def relative_folder(path: str) -> str:
    try:
        return str(PurePath(path).parent.relative_to(music_root()))
    except ValueError:
        return str(PurePath(path).parent)


def in_organised_folder(track: Track) -> bool:
    return any(ORGANISED_FOLDER.match(p) for p in PurePath(relative_folder(track.path)).parts)


def is_protected(path: str) -> bool:
    return any(part.lower() in PROTECTED_FOLDERS for part in PurePath(path).parts)


def default_keeps(group: list[Track]) -> list[Track]:
    """Copies kept by default: every copy in the numbered folders (the same track can deliberately live in
    TECH_HOUSE and UK_HOUSE) plus protected ones; the best copy if none is organised."""
    keeps = [t for t in group if in_organised_folder(t)] or [choose_keep(group)]
    keeps += [t for t in group if is_protected(t.path) and t not in keeps]
    return keeps


def keep_score(track: Track) -> tuple:
    """Higher is better: organised folder, quality, user data, depth, then oldest."""
    parts = PurePath(relative_folder(track.path)).parts
    return (
        in_organised_folder(track),
        Path(track.path).suffix.lower() in LOSSLESS,
        track.bitrate or 0,
        track.rating,
        len(track.tags),
        len(parts),
        -track.created_at.timestamp(),
    )


def choose_keep(copies: list[Track]) -> Track:
    return max(copies, key=keep_score)


def exact_duplicate_groups(session: Session) -> list[list[Track]]:
    hashes = select(Track.file_hash).group_by(Track.file_hash).having(func.count() > 1)
    groups: dict[str, list[Track]] = defaultdict(list)
    for track in session.scalars(select(Track).where(Track.file_hash.in_(hashes)).order_by(Track.path)):
        groups[track.file_hash].append(track)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0].path))


def normalize_title(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(original mix|extended mix|radio edit|clean|dirty)\b", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def probable_duplicate_groups(session: Session) -> list[list[Track]]:
    """Same artist + title and duration within 2 s, but different files (other encode, other tags)."""
    candidates = session.scalars(
        select(Track).where(Track.title.is_not(None), Track.duration_ms >= 60_000)
    ).all()
    by_name: dict[str, list[Track]] = defaultdict(list)
    for track in candidates:
        by_name[f"{normalize_title(track.artist)}|{normalize_title(track.title)}"].append(track)

    groups = []
    for tracks in by_name.values():
        if len({t.file_hash for t in tracks}) < 2:
            continue
        tracks.sort(key=lambda t: t.duration_ms)
        cluster = [tracks[0]]
        for track in tracks[1:]:
            if track.duration_ms - cluster[-1].duration_ms <= PROBABLE_DURATION_TOLERANCE_MS:
                cluster.append(track)
                continue
            if len({t.file_hash for t in cluster}) > 1:
                groups.append(cluster)
            cluster = [track]
        if len({t.file_hash for t in cluster}) > 1:
            groups.append(cluster)
    return sorted(groups, key=lambda g: (-len(g), g[0].path))


def merge_user_data(keep: Track, others: list[Track]) -> None:
    """The kept copy inherits the best rating, every tag and a genre if it has none."""
    keep.rating = max([keep.rating, *(t.rating for t in others)])
    present = {tt.tag_id for tt in keep.tags}
    for other in others:
        keep.genre = keep.genre or other.genre
        for tt in other.tags:
            if tt.tag_id not in present:
                keep.tags.append(TrackTag(tag_id=tt.tag_id, confidence=tt.confidence, source=tt.source))
                present.add(tt.tag_id)


def trash_tracks(session: Session, tracks: list[Track]) -> dict:
    """Move files to the Trash and drop their rows. Refuses anything outside MUSIC_ROOT."""
    root = music_root()
    removed, errors, freed = 0, [], 0
    for track in tracks:
        path = Path(track.path)
        if not path.is_relative_to(root):
            errors.append(f"{path}: outside the music folder, not touched")
            continue
        if is_protected(track.path):
            errors.append(f"{path}: managed by Apple Music, not touched")
            continue
        try:
            if path.exists():
                freed += path.stat().st_size
                send2trash(path)
            session.delete(track)
            removed += 1
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    session.commit()
    return {"removed": removed, "freed_bytes": freed, "errors": errors}


class CleanupError(ValueError):
    pass


def duplicate_groups(session: Session, kind: str) -> list[list[Track]]:
    return exact_duplicate_groups(session) if kind == "exact" else probable_duplicate_groups(session)


def resolve(session: Session, keep_id, remove_ids: list) -> dict:
    """Trash `remove_ids` after merging their rating/tags into `keep_id`."""
    if keep_id in remove_ids:
        raise CleanupError("The kept copy cannot also be removed")
    keep = session.get(Track, keep_id)
    others = list(session.scalars(select(Track).where(Track.id.in_(remove_ids))))
    if keep is None or len(others) != len(set(remove_ids)):
        raise LookupError("Unknown track")
    merge_user_data(keep, others)
    return trash_tracks(session, others)


def resolve_all_exact(session: Session) -> dict:
    """Byte-identical files only: every group keeps its default copies."""
    to_remove = []
    for group in exact_duplicate_groups(session):
        kept = default_keeps(group)
        others = [t for t in group if t not in kept]
        if others:
            merge_user_data(choose_keep(kept), others)
            to_remove.extend(others)
    return trash_tracks(session, to_remove)


def short_tracks(session: Session, max_ms: int, folders: set[str] | None = None) -> list[Track]:
    tracks = session.scalars(select(Track).where(Track.duration_ms < max_ms).order_by(Track.path))
    return [t for t in tracks if folders is None or relative_folder(t.path) in folders]


def short_summary(session: Session, max_ms: int) -> list[dict]:
    """Short tracks grouped by folder, biggest first; sample-pack folders are flagged."""
    by_folder: dict[str, list[Track]] = defaultdict(list)
    for track in short_tracks(session, max_ms):
        by_folder[relative_folder(track.path)].append(track)
    return [
        {
            "folder": folder,
            "count": len(tracks),
            "bytes": sum(t.file_size for t in tracks),
            "sample_folder": is_sample_folder(folder),
        }
        for folder, tracks in sorted(by_folder.items(), key=lambda item: -len(item[1]))
    ]
