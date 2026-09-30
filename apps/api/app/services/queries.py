"""Reusable SQL filters over the track catalogue."""

import re

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import aliased

from app.config import music_root
from app.models import Track


def folder_prefix(folder: str) -> str:
    return str(music_root() / folder.strip("/")) + "/"


def folder_filter(folder: str, column=Track.path):
    """Tracks inside `folder` (relative to MUSIC_ROOT) and all its subfolders."""
    return column.startswith(folder_prefix(folder), autoescape=True)


def dedupe_filter(folder: str | None = None):
    """One row per identical file (same SHA256).

    Inside a folder, duplicates are only collapsed within that folder, so browsing it shows all its tracks.
    Otherwise the copy kept is the one in the numbered folders (0X_...), like the cleanup suggestion.
    """
    # Aliased so SQLAlchemy does not correlate the subquery with the outer `tracks`.
    copy = aliased(Track)
    organised = copy.path.regexp_match(f"^{re.escape(str(music_root()))}/[0-9]+[_ -]")
    first_copies = (
        select(copy.id)
        .ext(distinct_on(copy.file_hash))
        .order_by(copy.file_hash, organised.desc(), copy.created_at, copy.path)
    )
    if folder:
        first_copies = first_copies.where(folder_filter(folder, copy.path))
    return Track.id.in_(first_copies)
