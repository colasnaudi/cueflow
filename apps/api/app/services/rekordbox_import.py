"""Import a Rekordbox collection export (File > Export Collection in xml format) — read-only.

Nothing is written to Rekordbox or to the audio files. Per matched track:
  * rating: Rekordbox's stars win over file tags, never over a rating changed in Cueflow (rating_source USER);
  * genre, label, BPM and key only fill empty catalogue fields (BPM/key source REKORDBOX);
  * a snapshot (its beatgrid, hot cues, comments...) is kept in rekordbox_tracks, e.g. to compare grids.
"""

import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from typing import BinaryIO
from urllib.parse import unquote, urlparse

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audio.keys import normalize_key
from app.models import Beatgrid, RekordboxTrack, Track


def decode_location(location: str) -> str:
    """file://localhost/Users/... -> /Users/... (NFC: Rekordbox and the filesystem may compose accents
    differently)."""
    return unicodedata.normalize("NFC", unquote(urlparse(location).path))


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse(source: BinaryIO) -> list[dict]:
    """TRACK entries of the COLLECTION, streamed (a whole library is tens of MB)."""
    tracks = []
    for _, element in ET.iterparse(source, events=("end",)):
        if element.tag != "TRACK" or not element.get("Location"):
            continue  # playlist entries only carry a Key
        a = element.attrib
        bpm = _number(a.get("AverageBpm"))
        tracks.append(
            {
                "location": decode_location(a["Location"]),
                "rekordbox_id": a.get("TrackID"),
                "name": a.get("Name") or None,
                "artist": a.get("Artist") or None,
                "genre": a.get("Genre") or None,
                "label": a.get("Label") or None,
                "comments": a.get("Comments") or None,
                "rating": min(5, int(_number(a.get("Rating")) or 0) // 51),
                "bpm": bpm if bpm else None,
                "tonality": a.get("Tonality") or None,
                "play_count": int(_number(a.get("PlayCount")) or 0),
                "date_added": _date(a.get("DateAdded")),
                "tempo": [
                    {
                        "inizio": _number(t.get("Inizio")),
                        "bpm": _number(t.get("Bpm")),
                        "battito": t.get("Battito"),
                    }
                    for t in element.findall("TEMPO")
                ],
                "position_marks": [
                    {
                        "name": m.get("Name"),
                        "type": m.get("Type"),
                        "start": _number(m.get("Start")),
                        "num": m.get("Num"),
                    }
                    for m in element.findall("POSITION_MARK")
                ],
            }
        )
        element.clear()
    return tracks


def import_collection(session: Session, source: BinaryIO) -> dict:
    entries = parse(source)
    by_path = {unicodedata.normalize("NFC", t.path): t for t in session.scalars(select(Track))}
    summary = defaultdict(int, entries=len(entries))

    for entry in entries:
        track = by_path.get(entry["location"])
        row = entry | {"track_id": track.id if track else None}
        session.execute(
            insert(RekordboxTrack)
            .values(**row)
            .on_conflict_do_update(
                index_elements=["location"], set_={k: v for k, v in row.items() if k != "location"}
            )
        )
        if track is None:
            summary["unmatched"] += 1
            continue
        summary["matched"] += 1
        summary["with_hot_cues"] += any(m["num"] not in (None, "-1") for m in entry["position_marks"])

        if track.rating_source != "USER":
            if entry["rating"] and (track.rating != entry["rating"] or track.rating_source != "REKORDBOX"):
                track.rating, track.rating_source = entry["rating"], "REKORDBOX"
                summary["ratings"] += 1
            elif not entry["rating"] and track.rating_source == "REKORDBOX":
                track.rating, track.rating_source = 0, None  # un-rated since the last import
                summary["ratings"] += 1
        if not track.genre and entry["genre"]:
            track.genre = entry["genre"]
            summary["genres"] += 1
        if not track.label and entry["label"]:
            track.label = entry["label"]
        if track.bpm is None and entry["bpm"]:
            track.bpm, track.bpm_source = round(entry["bpm"], 2), "REKORDBOX"
            summary["bpms"] += 1
        musical, camelot = normalize_key(entry["tonality"])
        if track.camelot_key is None and camelot:
            track.musical_key, track.camelot_key, track.key_source = musical, camelot, "REKORDBOX"
            summary["keys"] += 1
    session.commit()
    return dict(summary)


def grid_comparison(session: Session) -> dict:
    """Cueflow beatgrids vs Rekordbox's, per format: BPM agreement and the time offset of the grid phase.

    A consistent offset on MP3s only is the decoder start difference (REKORDBOX_MP3_OFFSET_MS)."""
    rows = session.execute(
        select(Track.path, Beatgrid, RekordboxTrack.tempo)
        .join(Beatgrid, Beatgrid.track_id == Track.id)
        .join(RekordboxTrack, RekordboxTrack.track_id == Track.id)
    ).all()
    by_kind: dict[str, dict[str, list]] = defaultdict(
        lambda: {"offsets": [], "bpm_same": [], "bar1_same": []}
    )
    for path, grid, tempo in rows:
        if not tempo or not tempo[0].get("bpm") or tempo[0].get("inizio") is None:
            continue
        theirs = tempo[0]
        kind = path.rsplit(".", 1)[-1].lower()
        bpm = float(grid.bpm)
        same_bpm = abs(bpm - theirs["bpm"]) < 0.05
        by_kind[kind]["bpm_same"].append(same_bpm)
        if not same_bpm:
            continue
        period = 60 / bpm
        ours = float(grid.first_beat)
        delta = (theirs["inizio"] - ours + period / 2) % period - period / 2
        by_kind[kind]["offsets"].append(delta * 1000)
        # Bar 1 agreement: Rekordbox's Battito tells which beat of the bar its Inizio is.
        their_bar_beat = (int(theirs.get("battito") or 1) - 1) % 4
        our_index = round((theirs["inizio"] - delta - ours) / period)
        our_bar_beat = (our_index - grid.downbeat_offset) % 4
        by_kind[kind]["bar1_same"].append(our_bar_beat == their_bar_beat)

    report = {}
    for kind, data in sorted(by_kind.items()):
        offsets = np.array(data["offsets"])
        report[kind] = {
            "tracks": len(data["bpm_same"]),
            "bpm_agreement": round(float(np.mean(data["bpm_same"])), 3) if data["bpm_same"] else None,
            "offset_ms_median": round(float(np.median(offsets)), 1) if len(offsets) else None,
            "offset_ms_iqr": [round(float(v), 1) for v in np.percentile(offsets, [25, 75])]
            if len(offsets)
            else None,
            "bar1_agreement": round(float(np.mean(data["bar1_same"])), 3) if data["bar1_same"] else None,
        }
    return report


if __name__ == "__main__":
    import json

    from app.db import SessionLocal

    with open(sys.argv[1], "rb") as source, SessionLocal() as session:
        print(json.dumps(import_collection(session, source), indent=2))
        print(json.dumps(grid_comparison(session), indent=2))
