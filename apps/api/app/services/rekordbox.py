"""Rekordbox XML export (the integration boundary, CLAUDE.md §19): Cueflow never touches Rekordbox's database.

Format: Pioneer "XML file format for playlists sharing" (DJ_PLAYLISTS 1.0.0). Positions are seconds; hot cues
are POSITION_MARK Num 0-7 (A-H), memory cues Num -1; TEMPO is the beatgrid (Inizio = a downbeat, Battito 1).
In Rekordbox: rekordbox xml tree -> select the tracks themselves -> right click -> "Import To Collection"
(importing only the playlist does not update tracks already in the collection).
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from app.models import Beatgrid, Cue, Track

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


def location(path: str) -> str:
    """file://localhost URI, percent-encoded like Rekordbox writes it."""
    return "file://localhost" + quote(path, safe="/")


def cue_time(grid: Beatgrid, bar: int, beat: int) -> float:
    period = 60 / float(grid.bpm)
    first_downbeat = float(grid.first_beat) + grid.downbeat_offset * period
    return first_downbeat + (bar * grid.beats_per_bar + beat) * period


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
) -> bytes:
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

        if grid is not None and include_beatgrid:
            ET.SubElement(
                node,
                "TEMPO",
                Inizio=f"{cue_time(grid, 0, 0) + offset:.3f}",
                Bpm=f"{float(grid.bpm):.2f}",
                Metro="4/4",
                Battito="1",
            )
        if grid is None:
            continue
        for cue in sorted(item.cues, key=lambda c: (c.type != "HOT", c.slot)):
            num = str(HOT_SLOTS.index(cue.slot)) if cue.type == "HOT" and cue.slot in HOT_SLOTS else "-1"
            ET.SubElement(
                node,
                "POSITION_MARK",
                Name=cue.label or "",
                Type="0",
                Start=f"{max(0.0, cue_time(grid, cue.bar, cue.beat) + offset):.3f}",
                Num=num,
                **_rgb(cue.color),
            )

    playlists = ET.SubElement(root, "PLAYLISTS")
    folder = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    playlist = ET.SubElement(
        folder,
        "NODE",
        Type="1",
        Name=name or f"Cueflow {datetime.now():%Y-%m-%d %H:%M}",
        KeyType="0",
        Entries=str(len(items)),
    )
    for track_id in range(1, len(items) + 1):
        ET.SubElement(playlist, "TRACK", Key=str(track_id))

    ET.indent(root)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def collect(session, folder: str | None, approved_only: bool) -> list[ExportItem]:
    """Analysed tracks of `folder` (all folders when None) that have cues; approved cues only if asked."""
    from sqlalchemy import select

    from app.services.cues import cues_of
    from app.services.queries import folder_filter

    query = select(Track, Beatgrid).join(Beatgrid, Beatgrid.track_id == Track.id).order_by(Track.path)
    if folder:
        query = query.where(folder_filter(folder))
    items = []
    for track, grid in session.execute(query):
        cues = cues_of(session, track.id)
        if approved_only:
            cues = [c for c in cues if c.approved]
        if not cues:  # a grid alone would overwrite the Rekordbox grid for nothing
            continue
        items.append(ExportItem(track, grid, cues))
    return items
