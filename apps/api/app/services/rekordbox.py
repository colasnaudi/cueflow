"""Rekordbox XML export (the integration boundary, CLAUDE.md §19): Cueflow never touches Rekordbox's database.

Format: Pioneer "XML file format for playlists sharing" (DJ_PLAYLISTS 1.0.0). Positions are seconds; hot cues
are POSITION_MARK Num 0-7 (A-H), memory cues Num -1; TEMPO is the beatgrid (Inizio = a downbeat, Battito 1).
In Rekordbox: rekordbox xml tree -> select the tracks themselves -> right click -> "Import To Collection"
(importing only the playlist does not update tracks already in the collection).
"""

import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from app.models import Beatgrid, Cue, RekordboxTrack, Track
from app.services.tempo import TempoMap, anchors_of

KINDS = {
    ".mp3": "MP3 File",
    ".wav": "WAV File",
    ".m4a": "M4A File",
    ".flac": "FLAC File",
    ".aif": "AIFF File",
    ".aiff": "AIFF File",
}
HOT_SLOTS = "ABCDEFGH"


@dataclass
class ExportItem:
    track: Track
    grid: Beatgrid | None
    cues: list[Cue]
    # The track's beatgrid in Rekordbox (from the last collection import), if any: the DJ's reference.
    rekordbox_tempo: list[dict] | None = None


def their_grid(item: ExportItem) -> tuple[float, float] | None:
    """(inizio, period) of the Rekordbox grid when it has Cueflow's tempo (one constant BPM), else None.
    None as well when the DJ edited the grid in Cueflow: that grid is exported and cues follow it."""
    tempo = item.rekordbox_tempo or []
    if not tempo or item.grid is None or tempo[0].get("inizio") is None or not tempo[0].get("bpm"):
        return None
    if _dj_grid(item):
        return None
    bpm = float(item.grid.bpm)
    if any(abs((t.get("bpm") or 0) - bpm) >= 0.05 for t in tempo):
        return None
    return float(tempo[0]["inizio"]), 60 / float(tempo[0]["bpm"])


def snap(time: float, inizio: float, period: float) -> float:
    """Nearest beat of the Rekordbox grid; a half-beat disagreement goes forward (Cueflow's offbeat grid puts
    a drop half a beat before the kick)."""
    return inizio + np.floor((time - inizio) / period + 0.55) * period


# Rekordbox matches the tracks of an imported XML to its collection by the exact Location string, so it must
# be encoded the way Rekordbox writes it (measured on a 6,079-track export): NFC, these ASCII characters left
# as they are, everything else (space ' & [ ] % and non-ASCII bytes) as lowercase %xx.
REKORDBOX_LITERAL = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_.-:()!,*@+$=#;?~"
)


def location(path: str) -> str:
    """file://localhost URI, encoded exactly like Rekordbox writes it."""
    encoded = "".join(
        char if char in REKORDBOX_LITERAL else "".join(f"%{byte:02x}" for byte in char.encode("utf-8"))
        for char in unicodedata.normalize("NFC", path)
    )
    return "file://localhost" + encoded


def _dj_grid(item: ExportItem) -> bool:
    """A grid set or corrected in Cueflow is the DJ's latest word: it replaces the one in Rekordbox."""
    return item.grid is not None and item.grid.source == "USER"


def cue_time(grid: Beatgrid, bar: int, beat: float) -> float:
    return TempoMap.of(grid).time_of(bar, beat)


def _place(time: float, offset: float, reference: tuple[float, float] | None) -> float:
    return snap(time, *reference) if reference else time + offset


def _tempo_entries(node: ET.Element, grid: Beatgrid, offset: float) -> None:
    if not grid.anchors:  # constant grid: one entry on bar 1
        attributes = {"Inizio": f"{cue_time(grid, 0, 0) + offset:.3f}", "Bpm": f"{float(grid.bpm):.2f}"}
        ET.SubElement(node, "TEMPO", attributes, Metro="4/4", Battito="1")
        return
    for anchor in anchors_of(grid):
        ET.SubElement(
            node,
            "TEMPO",
            Inizio=f"{anchor.time + offset:.3f}",
            Bpm=f"{anchor.bpm:.2f}",
            Metro="4/4",
            Battito=str(anchor.beat),
        )


def _rgb(color: str | None) -> dict[str, str]:
    if not color or len(color) != 7:
        return {}
    return {
        "Red": str(int(color[1:3], 16)),
        "Green": str(int(color[3:5], 16)),
        "Blue": str(int(color[5:7], 16)),
    }


def build(
    items: list[ExportItem],
    include_beatgrid: bool = True,
    mp3_offset_ms: float = 0.0,
    name: str | None = None,
    folder_tree: Path | None = None,
) -> bytes:
    """`folder_tree`: the music root — playlists then mirror the folders under it instead of one playlist."""
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name="Cueflow", Version="0.4.0", Company="Cueflow")
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(items)))

    for track_id, item in enumerate(items, start=1):
        track, grid = item.track, item.grid
        suffix = Path(track.path).suffix.lower()
        # Decoders disagree on where an MP3 starts (encoder delay): a configurable shift for MP3s only.
        offset = mp3_offset_ms / 1000 if suffix == ".mp3" else 0.0
        attributes = {
            "TrackID": str(track_id),
            "Name": track.title or track.filename,
            "Artist": track.artist or "",
            "Album": track.album or "",
            "Genre": track.genre or "",
            "Kind": KINDS.get(suffix, "Audio File"),
            "Size": str(track.file_size),
            "TotalTime": str(round((track.duration_ms or 0) / 1000)),
            "AverageBpm": f"{float(grid.bpm if grid else track.bpm or 0):.2f}",
            "Tonality": track.musical_key or "",
            "Location": location(track.path),
        }
        if track.bitrate:
            attributes["BitRate"] = str(track.bitrate)
        if track.sample_rate:
            attributes["SampleRate"] = str(track.sample_rate)
        if track.rating:  # 0 would wipe a rating set in Rekordbox
            attributes["Rating"] = str(track.rating * 51)
        node = ET.SubElement(collection, "TRACK", attributes)

        reference = their_grid(item)
        # Never replace a grid the DJ already has in Rekordbox (cues are aligned on it instead), unless the DJ
        # edited the grid in Cueflow.
        if grid is not None and include_beatgrid and (_dj_grid(item) or not item.rekordbox_tempo):
            _tempo_entries(node, grid, offset)
        if grid is None:
            continue
        for cue in sorted(item.cues, key=lambda c: (c.type != "HOT", c.slot)):
            num = str(HOT_SLOTS.index(cue.slot)) if cue.type == "HOT" and cue.slot in HOT_SLOTS else "-1"
            start = max(0.0, _place(cue_time(grid, cue.bar, cue.beat), offset, reference))
            mark = {"Name": cue.label or "", "Type": "0", "Start": f"{start:.3f}", "Num": num}
            if cue.loop_beats:  # a loop: Type 4 with its end
                end = cue_time(grid, cue.bar, cue.beat + float(cue.loop_beats))
                mark.update(Type="4", End=f"{max(start, _place(end, offset, reference)):.3f}")
            ET.SubElement(node, "POSITION_MARK", mark, **_rgb(cue.color))

    playlists = ET.SubElement(root, "PLAYLISTS")
    if folder_tree is not None:
        _folder_playlists(playlists, items, folder_tree)
    else:
        folder = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
        _playlist(folder, name or f"Cueflow {datetime.now():%Y-%m-%d %H:%M}", range(1, len(items) + 1))

    ET.indent(root)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def collect(session, folder: str | None, approved_only: bool) -> list[ExportItem]:
    """Analysed tracks of `folder` (all folders when None) that have cues; approved cues only if asked."""
    from sqlalchemy import select

    from app.services.cues import cues_of
    from app.services.queries import folder_filter

    query = (
        select(Track, Beatgrid, RekordboxTrack.tempo)
        .join(Beatgrid, Beatgrid.track_id == Track.id)
        .outerjoin(RekordboxTrack, RekordboxTrack.track_id == Track.id)
        .order_by(Track.path)
    )
    if folder:
        query = query.where(folder_filter(folder))
    items = []
    for track, grid, rekordbox_tempo in session.execute(query):
        cues = cues_of(session, track.id)
        if approved_only:
            cues = [c for c in cues if c.approved]
        if not cues:  # a grid alone would overwrite the Rekordbox grid for nothing
            continue
        items.append(ExportItem(track, grid, cues, rekordbox_tempo))
    return items


def _playlist(parent: ET.Element, name: str, track_ids) -> None:
    ids = list(track_ids)
    node = ET.SubElement(parent, "NODE", Type="1", Name=name, KeyType="0", Entries=str(len(ids)))
    for track_id in ids:
        ET.SubElement(node, "TRACK", Key=str(track_id))


def _folder_playlists(playlists: ET.Element, items: list[ExportItem], root: Path) -> None:
    """Rekordbox folders mirroring the music folders. A folder with sub-folders gets an "All tracks" playlist
    (everything below it, to import a whole branch at once) next to its sub-folders."""
    tree: dict = {}
    for track_id, item in enumerate(items, start=1):
        try:
            parts = Path(item.track.path).relative_to(root).parts[:-1]
        except ValueError:
            parts = ()
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
        node.setdefault("__tracks__", []).append(track_id)

    def all_ids(node: dict) -> list[int]:
        return node.get("__tracks__", []) + [
            i for k, child in node.items() if k != "__tracks__" for i in all_ids(child)
        ]

    def add(parent: ET.Element, name: str, node: dict) -> None:
        children = sorted((k for k in node if k != "__tracks__"), key=str.lower)
        if not children:
            _playlist(parent, name, node.get("__tracks__", []))
            return
        folder = ET.SubElement(parent, "NODE", Type="0", Name=name, Count=str(len(children) + 1))
        _playlist(folder, f"{name} · all tracks", all_ids(node))
        for child in children:
            add(folder, child.replace(":", "/"), node[child])

    top = sorted((k for k in tree if k != "__tracks__"), key=str.lower)
    root_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")  # Count = child nodes
    has_edits = any(item.track.edited_from is not None for item in items)
    cueflow = ET.SubElement(root_node, "NODE", Type="0", Name="Cueflow", Count=str(len(top) + 1 + has_edits))
    _playlist(cueflow, "All analysed tracks", range(1, len(items) + 1))
    edits = [i for i, item in enumerate(items, start=1) if item.track.edited_from is not None]
    if edits:  # exported from the audio editor, outside the music folders
        _playlist(cueflow, "Edits", edits)
    for name in top:
        add(cueflow, name.replace(":", "/"), tree[name])


def live_path() -> Path:
    from app.config import get_settings

    settings = get_settings()
    return (
        Path(settings.rekordbox_xml_path)
        if settings.rekordbox_xml_path
        else settings.data_dir / "rekordbox" / "cueflow.xml"
    )


def write_live(session) -> dict:
    """The XML Rekordbox is pointed at once: every analysed track with cues, playlists mirroring the folders.
    Written atomically so Rekordbox never reads a half-written file."""
    from app.config import get_settings, music_root

    settings = get_settings()
    items = collect(session, None, approved_only=True)
    xml = build(
        items, include_beatgrid=True, mp3_offset_ms=settings.rekordbox_mp3_offset_ms, folder_tree=music_root()
    )
    path = live_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(xml)
    tmp.replace(path)
    return live_status(len(items))


def live_status(tracks: int | None = None) -> dict:
    path = live_path()
    return {
        "path": str(path),
        "exists": path.exists(),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime) if path.exists() else None,
        "tracks": tracks,
    }
