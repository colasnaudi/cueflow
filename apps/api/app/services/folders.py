"""Folder tree of the library and genre hints from the user's own folder organisation."""

import re
from pathlib import Path, PurePath

# Only folders below a "…GENRES" folder are treated as a genre (e.g. 02_GENRES/HOUSE/TECH_HOUSE).
GENRES_DIR = re.compile(r"^(\d+[_ -]*)?genres?$", re.IGNORECASE)
# DJ tools / sample packs are not genres.
NOT_A_GENRE = re.compile(r"^(tools?|samples?|vocals?|vox|fx|acapellas?|loops?)$", re.IGNORECASE)
UPPERCASE_WORDS = {"uk", "us", "dj", "edm", "fr", "ukg", "dnb", "r&b", "90s", "80s"}


def folder_label(name: str) -> str:
    """'TECH_HOUSE' -> 'Tech House', 'RAP:HIP_HOP' -> 'Rap/Hip Hop' (':' is how Finder's '/' is stored)."""
    name = re.sub(r"^\d+[_ -]+", "", name).replace(":", "/").replace("_", " ")
    words = re.sub(r"\s+", " ", name).strip().split(" ")
    return " ".join(
        w.upper() if w.lower() in UPPERCASE_WORDS else "/".join(p.capitalize() for p in w.split("/"))
        for w in words
    )


def folder_genre(path: str | Path, root: Path) -> str | None:
    """Genre implied by where the file lives, or None."""
    try:
        parts = PurePath(path).relative_to(root).parts[:-1]
    except ValueError:
        return None
    for index, part in enumerate(parts):
        if GENRES_DIR.match(part):
            below = parts[index + 1 :]
            if not below or any(NOT_A_GENRE.match(p) for p in below):
                return None
            return folder_label(below[-1])
    return None


def is_sample_folder(path: str | Path) -> bool:
    return any(NOT_A_GENRE.match(part) for part in PurePath(path).parts)


def build_tree(files: list[tuple[str, str | None]], root: Path) -> list[dict]:
    """Nested folders with recursive counts of (path, hash) pairs; a hash is counted once per folder.

    Pass None as hash to count every file. Files directly in `root` are not a folder.
    """
    tree: dict = {}
    for path, file_hash in files:
        try:
            parts = PurePath(path).relative_to(root).parts[:-1]
        except ValueError:
            continue
        node = tree
        for depth, part in enumerate(parts):
            entry = node.setdefault(
                part, {"path": "/".join(parts[: depth + 1]), "keys": set(), "children": {}}
            )
            entry["keys"].add(file_hash or path)
            node = entry["children"]

    def to_list(nodes: dict) -> list[dict]:
        return [
            {
                "name": name,
                "path": entry["path"],
                "count": len(entry["keys"]),
                "children": to_list(entry["children"]),
            }
            for name, entry in sorted(nodes.items(), key=lambda item: item[0].lower())
        ]

    return to_list(tree)
