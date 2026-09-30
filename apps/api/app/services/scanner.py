"""Library scanner: walk a folder, hash + read tags of new/changed files, upsert them into `tracks`.

Run standalone with `pnpm scan [folder]`, or through POST /library/scan.
"""

import hashlib
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio.metadata import AUDIO_EXTENSIONS, read_metadata
from app.config import get_settings, music_root
from app.db import SessionLocal
from app.models import Track

log = logging.getLogger(__name__)

HASH_CHUNK = 1024 * 1024
COMMIT_EVERY = 200


@dataclass
class ScanStatus:
    state: str = "idle"  # idle | running | completed | failed
    running: bool = False
    error: str | None = None
    root: str | None = None
    total: int = 0
    processed: int = 0
    added: int = 0
    updated: int = 0
    moved: int = 0
    unchanged: int = 0
    missing: int = 0
    excluded: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None

    def as_dict(self) -> dict:
        return asdict(self) | {"errors": self.errors[-20:], "error_count": len(self.errors)}


status = ScanStatus()
_lock = threading.Lock()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def excluded_dirs() -> set[str]:
    return {name.lower() for name in get_settings().scan_exclude_dirs}


def is_excluded(path: str | Path, root: Path) -> bool:
    try:
        parts = Path(path).relative_to(root).parts[:-1]
    except ValueError:
        return False
    return any(part.lower() in excluded_dirs() for part in parts)


def find_audio_files(root: Path) -> list[Path]:
    files = []
    skip = excluded_dirs()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in skip]
        for name in filenames:
            if not name.startswith(".") and Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                files.append(Path(dirpath) / name)
    return files


def _inspect(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path),
        "filename": path.name,
        "file_hash": sha256_file(path),
        "file_size": stat.st_size,
        "file_mtime_ns": stat.st_mtime_ns,
        **read_metadata(path).as_dict(),
    }


def _apply(session: Session, data: dict, by_path: dict[str, Track], by_hash: dict[str, list[Track]]) -> str:
    """Insert or update one track. Returns which counter to bump."""
    if (track := by_path.get(data["path"])) is not None:
        outcome = "updated"
    else:
        # Same content at a path that no longer exists: the file was moved/renamed, keep its history.
        moved_from = next((t for t in by_hash.get(data["file_hash"], []) if not os.path.exists(t.path)), None)
        if moved_from is not None:
            track, outcome = moved_from, "moved"
            by_path.pop(track.path, None)
        else:
            track, outcome = Track(), "added"
            session.add(track)

    # Never overwrite a user-set rating with the file's POPM value.
    if outcome != "added" and track.rating:
        data = {k: v for k, v in data.items() if k != "rating"}
    for key, value in data.items():
        setattr(track, key, value)
    by_path[track.path] = track
    by_hash.setdefault(track.file_hash, []).append(track)
    return outcome


def scan(root: str | Path, workers: int = 8) -> ScanStatus:
    global status
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    with _lock:
        if status.running:
            raise RuntimeError("A scan is already running")
        status = ScanStatus(state="running", running=True, root=str(root), started_at=time.time())

    try:
        files = find_audio_files(root)
        status.total = len(files)
        with SessionLocal() as session:
            known = session.scalars(select(Track)).all()
            # Rows indexed before a folder was excluded: forget them (the files are not touched).
            for track in [t for t in known if is_excluded(t.path, root)]:
                session.delete(track)
                status.excluded += 1
            session.flush()
            known = [t for t in known if not is_excluded(t.path, root)]
            by_path = {t.path: t for t in known}
            by_hash: dict[str, list[Track]] = {}
            for t in known:
                by_hash.setdefault(t.file_hash, []).append(t)

            todo = []
            for path in files:
                track = by_path.get(str(path))
                try:
                    stat = path.stat()
                except OSError as exc:
                    status.errors.append(f"{path}: {exc}")
                    continue
                if track and track.file_size == stat.st_size and track.file_mtime_ns == stat.st_mtime_ns:
                    status.unchanged += 1
                    status.processed += 1
                else:
                    todo.append(path)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_inspect, path): path for path in todo}
                for pending, future in enumerate(as_completed(futures), start=1):
                    path = futures[future]
                    try:
                        outcome = _apply(session, future.result(), by_path, by_hash)
                        setattr(status, outcome, getattr(status, outcome) + 1)
                    except Exception as exc:  # one broken file must not abort the whole scan
                        log.warning("scan failed for %s: %s", path, exc)
                        status.errors.append(f"{path}: {exc}")
                    status.processed += 1
                    if pending % COMMIT_EVERY == 0:
                        session.commit()
            session.commit()

            prefix = str(root) + os.sep
            status.missing = sum(1 for p in by_path if p.startswith(prefix) and not os.path.exists(p))
        status.state = "completed"
    except Exception as exc:
        status.state, status.error = "failed", str(exc)
        raise
    finally:
        status.running = False
        status.finished_at = time.time()
    return status


def resolve_scan_root(path: str | None) -> Path:
    """Folder to scan from an API request: MUSIC_ROOT or one of its sub-folders, nothing else."""
    root = music_root()
    target = (
        (root / path if path and not Path(path).is_absolute() else Path(path or root)).expanduser().resolve()
    )
    if not target.is_relative_to(root):
        raise ValueError(f"Only folders inside {root} can be scanned")
    if not target.is_dir():
        raise ValueError(f"Not a folder: {target}")
    return target


def start_in_background(root: Path) -> None:
    if status.running:
        raise RuntimeError("A scan is already running")

    def run() -> None:
        try:
            scan(root)
        except Exception:  # already recorded in status (state=failed); keep the traceback in the logs
            log.exception("library scan failed")

    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    target = sys.argv[1] if len(sys.argv) > 1 else get_settings().music_root
    done = {"flag": False}

    def report() -> None:
        while not done["flag"]:
            time.sleep(2)
            print(f"\r{status.processed}/{status.total} files", end="", flush=True)

    threading.Thread(target=report, daemon=True).start()
    result = scan(target)
    done["flag"] = True
    summary = result.as_dict()
    print(f"\nScanned {result.root} in {result.finished_at - result.started_at:.1f}s")
    for key in ("total", "added", "updated", "moved", "unchanged", "missing", "excluded", "error_count"):
        print(f"  {key:<12}{summary[key]}")
    for error in summary["errors"]:
        print(f"  ! {error}")
