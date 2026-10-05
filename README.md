# Cueflow

Cueflow is a local DJ library manager for House, Tech House and UK House
libraries. It scans a music folder, normalises the metadata in a searchable
catalogue, lets you preview and organise tracks, suggests genres with local
audio analysis, and helps clean up duplicates and short files.

Cueflow is deliberately non-destructive:

- it never rewrites the tags inside your audio files;
- genre suggestions are reviewed before they are applied to the catalogue;
- cleanup actions move files to the macOS Trash instead of permanently deleting
  them;
- the AI does not write directly to Rekordbox.

## Current status

The current application implements the MVP 0.1 library workflow plus genre
review and cleanup tools:

| Area | Status |
| --- | --- |
| Scan and incremental sync | Available |
| Metadata extraction and normalisation | Available |
| Library search, filters and sorting | Available |
| Folder browser | Available |
| Audio player and waveform | Available |
| Manual ratings and tags | Available |
| Key- and BPM-compatible track matching | Available |
| Genre suggestions and review queue | Available |
| Duplicate and short-track cleanup | Available |
| BPM, beatgrid, bar 1, key, energy, structure and vocals from audio | Available (MVP 0.2) |
| Ollama classification, embeddings and cue suggestions | Planned for MVP 0.3 |
| Hot/memory cue suggestions and Rekordbox XML export | Available |
| Cue editor and Rekordbox XML import | Available |
| Audio editor (cut/copy/paste, fades, gain, A/B, export as a new file) | Available |
| DJ preparation in the editor (beatgrid, cues, loops, sections, notes) | Available |
| Editor effects, pitch shift and time stretch | Planned (editor V2 lot 2) |
| Playlists and AI set builder | Planned |

## Features

### Library scanning

The scanner recursively indexes `.mp3`, `.wav`, `.flac`, `.aiff`, `.aif` and
`.m4a` files below `MUSIC_ROOT`. It:

- computes a SHA-256 hash for every file;
- reads metadata from ID3, MP4 and Vorbis tags;
- falls back to `Artist - Title` or the filename when tags are incomplete;
- reads duration, bitrate and sample rate, using FFmpeg when necessary;
- imports BPM and musical key when they are present in the file;
- normalises musical keys and derives Camelot keys;
- converts ID3 POPM ratings to the five-star rating used by the UI;
- skips unchanged files using file size and modification time;
- detects moved or renamed files by their hash and keeps their catalogue
  history;
- reports added, updated, moved, unchanged, missing, excluded and failed
  files;
- ignores hidden directories and configured application directories such as
  `rekordbox` and `Ableton`.

Scanning can be started from the sidebar or from the command line. It runs in
the background and exposes live progress in the UI.

### Library browsing, search and filters

The library view provides:

- full-text search over artist, title, album, label and filename;
- filters for genre, BPM range, Camelot key, minimum rating and tags;
- a minimum-duration filter for excluding samples;
- an optional duplicate view that shows one copy per SHA-256 hash;
- sorting by artist, title, BPM, key, genre, rating, duration or date added;
- infinite scrolling through large libraries;
- result facets showing available genres, keys and BPM bounds;
- folders and all their subfolders as a navigable tree;
- breadcrumbs when browsing a folder;
- saved views for all tracks, recently added tracks and favourites.

The sidebar also shows the number of pending genre reviews and the most useful
library folders.

### Track details and playback

Each track has a detail page with:

- play/pause controls and previous/next navigation;
- artist, title, album, label, year, format, bitrate and sample rate;
- duration, BPM, musical key and Camelot key;
- a server-computed RMS waveform rendered with WaveSurfer.js;
- click-to-seek playback;
- manual five-star rating;
- add/remove manual tags with normalised uppercase names;
- the original file path and the current catalogue status.

The shared player remains visible while browsing the application. Keyboard
shortcuts are:

| Shortcut | Action |
| --- | --- |
| `Space` | Play or pause |
| `Shift + Left` | Previous track |
| `Shift + Right` | Next track |
| `Cmd/Ctrl + K` | Focus search |
| Double-click a row | Start playback |

The “Match playing” filter finds tracks whose keys are compatible with the
track currently loaded in the player (same key, relative key or adjacent
Camelot key) and whose BPM is within ±3%.

### Audio analysis

“Analyse audio” (sidebar) or “Analyse now / Re-analyse” (track page) runs a
deterministic analysis of the audio; nothing is written to the files:

- **BPM and beatgrid** — one constant grid fitted to the whole track and snapped
  to integer tempos, then slid onto the kick attacks.
- **Bar 1** — the `beat_this` downbeat model, then moved onto the drops when
  they agree on another beat of the bar. It can be moved by one beat by hand;
  a corrected grid is never overwritten.
- **Key** (Essentia `bgate` profile), **energy** per bar and **vocals** per bar.
- **Structure** — INTRO, GROOVE, BREAK, BUILD, DROP, OUTRO from per-bar kick,
  bass, mid and high levels. A DROP needs kick **and** bass at full level for
  at least 8 bars, so fake drops, kick rolls and filter openings stay in the
  BUILD. Drops are placed to the beat where kick and bass come back, without
  snapping to 4-bar phrases. Regression fixtures measured on ten real tracks
  live in `apps/api/tests/fixtures/structure`.

### Cues and Rekordbox export

After analysis each track gets suggested hot cues — A START, B GROOVE, C BREAK,
D DROP, E VOCAL, F DROP 2, G OUTRO — placed to the beat from its sections, plus
a memory cue on every section start. They are approved automatically
(`AUTO_APPROVE_CUES=true`), so one “Analyse audio” run leaves the whole library
ready to export; fix them later in Rekordbox. On the track page you can listen,
remove a cue, or “Lock cues” so that a later re-analysis keeps them as they are.

After every audio analysis Cueflow also rewrites one **live XML**
(`data/rekordbox/cueflow.xml`, or `REKORDBOX_XML_PATH`) with every analysed
track, its cues and playlists mirroring your folders. Point Rekordbox to it once
(Preferences → Advanced → Database → rekordbox xml → Imported Library); then,
whenever you want, open rekordbox xml → Cueflow → a folder, select the tracks
and “Import To Collection”. No download needed.

**Import your Rekordbox collection** (Rekordbox → File → Export Collection in
xml format, then “Import your Rekordbox collection” on the Rekordbox page):
ratings come from Rekordbox (never over a rating changed in Cueflow), missing
BPM/keys/genres are filled, and each track's Rekordbox beatgrid is kept. When a
track has a grid in Rekordbox, the exported XML does **not** replace it: Cueflow's
cues are snapped onto that grid instead (Cueflow's cues do replace the hot cues
already in Rekordbox, by the DJ's choice).

Right-click a folder in the sidebar to analyse its audio and cues, re-analyse
it, suggest genres, rescan it, download its XML or show it in the Finder.

“Rekordbox export” also builds a `rekordbox.xml` (a copy is kept in `data/exports/`)
for a folder, with approved cues by default and optionally the beatgrid. In
Rekordbox: set the file under Preferences → Advanced → Database → rekordbox
xml, show “rekordbox xml” in the tree, open the Cueflow playlist, select the
**tracks** and choose “Import To Collection”. Back up the Rekordbox library
first: the import overwrites the cues (and grids) of those tracks. Cueflow never
touches the Rekordbox database. `REKORDBOX_MP3_OFFSET_MS` shifts MP3 positions
if your Rekordbox decodes MP3s with another start offset (about one MP3 frame,
26 ms, for some files).

BPM and key are only written to the catalogue when the file tags have none; a
differing tag is shown on the track page and replaced only on request.
Analysis takes about 7-12 s per track (`ANALYSIS_WORKERS` processes in
parallel).

### Audio editor

“Open in Editor” on a track page opens a minimal audio editor. The original file
is only ever read: an edit is a list of slices of the original (plus fades and a
gain) kept in the catalogue (`track_edits`), and audio is rendered only on
export.

- waveform with time ruler, zoom (`+`/`-`, ⌘/Ctrl + wheel), overview strip,
  click to place the playhead, drag to select, drag a selection edge to move it,
  double-click to select a segment;
- Cut, Copy, Paste (at the playhead), Duplicate, Delete, Trim, Split, Fade in/out
  over the selection, global gain (±12 dB) and Normalize (peak to −1 dBFS);
- undo/redo for every edit (⌘Z / ⌘⇧Z), Save edit (⌘S), Reset to original
  (confirmed);
- play/pause, stop, play the selection, loop it, A/B between the original and
  the edit at the same musical moment;
- Export writes `<file> (Edited).wav|mp3` (WAV 16/24-bit, MP3 192–320 kbps, tags
  copied from the original) in `EDITS_DIR` (default `data/edits/`, outside the
  library). An existing file is never overwritten: the next one is
  `(Edited 2)`.

The browser previews the same decode the export uses (`/tracks/{id}/edit/source`),
so what you hear is what gets exported.

#### DJ preparation (editor tabs)

The editor's tabs prepare the track for a set; everything is saved right away in
the catalogue, on the original track, and shown on the waveform (on B, wherever
that audio is still heard):

- **Beatgrid** — BPM ±0.01/0.1/1, ×2, ÷2, move the grid by 1/10 ms, “Bar 1
  here”, tap tempo (T), and tempo changes for tracks whose tempo moves. A grid
  edited in Cueflow survives re-analysis and replaces the grid in Rekordbox on
  import.
- **Cues** — hot cues A–H and memory cues at the playhead (C / M), dragged on
  the waveform, named, coloured. Positions snap to the beat.
- **Loops** — 1/2 to 32 beats at the playhead (L), memory or hot loops, moved
  and resized on the waveform, played in a loop, duplicated. Exported as
  Rekordbox loops.
- **Sections** — the detected structure can be corrected: type (Intro, Verse,
  Build, Drop, Break, Chorus, Bridge, Outro, Custom…), name, colour, split,
  merge, drag the boundaries. Your sections replace the detected ones (which
  can be restored) and drive the generated memory cues.
- **Notes** — 📝 🔴 🗣 ⚠️ 🔥 notes on the timeline (N), kept in Cueflow.
- **Key** — corrected from the header (Camelot and musical name).

An exported edit is added to the library with its preparation carried through
the cuts (grid, cues, loops, sections, notes), so it appears in the Rekordbox XML
(“Edits” playlist) without a new analysis.

### Genre Review

The `/review` view turns genre classification into a review queue instead of
silently changing the library:

1. folder names are interpreted as genre hints (for example,
   `02_GENRES/HOUSE/TECH_HOUSE`);
2. Essentia's Discogs-EffNet model analyses tracks that need a suggestion;
3. the service returns the best matching styles from its 400-style taxonomy;
4. folder and audio suggestions are displayed with their source and
   confidence;
5. you approve the suggested genre, choose another genre, reject it, or undo
   a previous decision;
6. identical copies of a file receive the same reviewed genre.

The analysis job runs in the background, reports progress, can be stopped, and
refreshes the review queue while it runs. The first use downloads the required
Essentia model files into `data/models/` (about 20 MB). The audio model takes
approximately 1.5 seconds per track on the target local setup.

Review actions only update Cueflow's database. They never modify the source
audio tags.

### Cleanup

The `/cleanup` view contains two cleanup workflows.

#### Duplicates

- **Identical files** are grouped by SHA-256 and can be resolved one group at
  a time or all at once.
- **Probable duplicates** are grouped when artist, title and duration suggest
  that files may be alternate encodes or edits.
- You choose which copies to keep and can preview them before acting.
- Copies in numbered organisation folders are kept by default.
- Apple Music files are protected by default.
- Ratings and tags from removed copies are merged into the kept copy.

#### Short tracks

- Choose a threshold of 15, 30, 60, 90 or 120 seconds.
- Results are grouped by folder and can be expanded for a quick preview.
- Folders that look like DJ tools or sample packs (`TOOLS`, `VOCALS`, `VOX`,
  and similar names) are not selected by default.
- Select folders and move their short files to the Trash after confirmation.

All cleanup operations are reversible through the macOS Trash. Cueflow does
not permanently delete files.

## Architecture

```text
┌─────────────────────────────┐
│ Next.js web app :3000       │
│ Library · Review · Cleanup  │
└──────────────┬──────────────┘
               │ REST
               ▼
┌─────────────────────────────┐
│ FastAPI API :8000           │
│ tracks · folders · analysis │
│ review · cleanup · media    │
└───────┬──────────┬──────────┘
        │          │
        ▼          ▼
 PostgreSQL    Local audio files
 + pgvector    + FFmpeg/Essentia
```

The repository is a monorepo:

```text
apps/web        Next.js frontend
apps/api        FastAPI backend and audio services
packages/types  Shared TypeScript API types
db/migrations   Alembic migrations
docker/         PostgreSQL + pgvector Compose setup
data/           Generated waveform and model/cache data
scripts/        Local development utilities
```

## Stack

| Part | Technology |
| --- | --- |
| Web | Next.js 16, React 19, TypeScript |
| UI | Tailwind CSS 4, shadcn/ui |
| Client state/data | TanStack Query, Zustand |
| Playback | WaveSurfer.js and the browser audio element |
| API | FastAPI, Pydantic, SQLAlchemy 2.1 |
| Database | PostgreSQL 17 with pgvector |
| Migrations | Alembic |
| Metadata | mutagen and FFmpeg/ffprobe |
| Audio genre analysis | Essentia TensorFlow, Discogs-EffNet |
| Future local AI | Ollama with `gemma4:12b-it-qat` and `embeddinggemma` |

## Requirements

- Docker
- Node.js 22
- pnpm 10
- [uv](https://docs.astral.sh/uv/)
- FFmpeg
- macOS for the Trash-based cleanup workflow
- Optional: Ollama for the planned AI features

## Getting started

```bash
cp .env.example .env
# Set MUSIC_ROOT to the folder containing your music
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000). The FastAPI
documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs)
and the health endpoint is [http://localhost:8000/health](http://localhost:8000/health).

`pnpm dev` starts PostgreSQL, applies pending migrations, and runs the API and
web app with reload enabled. PostgreSQL is exposed on port `5433` so it does
not conflict with a local PostgreSQL installation.

### Environment variables

Copy [.env.example](/Users/colasnaudi/Developer/Github/cueflow/.env.example)
and adjust:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection | `localhost:5433/cueflow` |
| `MUSIC_ROOT` | Default folder for scans | — |
| `NEXT_PUBLIC_API_URL` | API URL used by the web app | `http://localhost:8000` |
| `OLLAMA_URL` | Future Ollama endpoint | `http://localhost:11434` |
| `OLLAMA_LLM_MODEL` | Future local LLM | `gemma4:12b-it-qat` |
| `OLLAMA_EMBED_MODEL` | Future embedding model | `embeddinggemma` |
| `EMBEDDING_DIM` | Future vector dimension | `768` |
| `EDITS_DIR` | Where the audio editor exports edited files | `data/edits/` |

## Commands

| Command | Description |
| --- | --- |
| `pnpm dev` | Start PostgreSQL, migrations, API and web with reload |
| `pnpm db:up` | Start PostgreSQL and wait until it is healthy |
| `pnpm db:down` | Stop PostgreSQL while keeping its Docker volume |
| `pnpm scan` | Scan `MUSIC_ROOT` from the command line |
| `pnpm scan /path/to/music` | Scan a specific folder |
| `pnpm scan --reread` | Also re-read the tags of unchanged files (after a reader update) |
| `pnpm test` | Run the API test suite against a throwaway test database |

## API surface

The FastAPI service currently exposes:

- `GET /health` — health check;
- `GET /tracks` and `GET /tracks/{id}` — search, filter and read tracks;
- `PATCH /tracks/{id}` — update catalogue rating and metadata fields;
- `GET /tracks/{id}/audio` — stream a track;
- `GET /tracks/{id}/peaks` — retrieve waveform peaks;
- `POST /tracks/{id}/tags` and `DELETE /tracks/{id}/tags/{tag_id}` — manage
  tags;
- `GET/POST /tracks/{id}/analysis`, `POST /tracks/{id}/analysis/apply` and
  `POST /tracks/{id}/beatgrid/shift` — read or run a track's audio analysis,
  use its BPM/key, move bar 1;
- `GET/POST /analysis/audio` and `POST /analysis/audio/stop` — library-wide
  audio analysis;
- `GET /tracks/{id}/cues`, `POST /tracks/{id}/cues/approve`,
  `POST /tracks/{id}/cues/regenerate` and `DELETE /tracks/{id}/cues/{cue_id}` —
  review the suggested cues;
- `POST /tracks/{id}/cues` and `PATCH /tracks/{id}/cues/{cue_id}` — place,
  move, rename or resize (loops) cues;
- `PUT /tracks/{id}/beatgrid` — the DJ's beatgrid (with tempo changes);
- `PUT/DELETE /tracks/{id}/sections` — the DJ's sections / back to the detected
  ones;
- `/tracks/{id}/annotations` — timeline notes;
- `GET /export/rekordbox/preview` and `POST /export/rekordbox` — build the
  Rekordbox XML;
- `GET/PUT/DELETE /tracks/{id}/edit`, `GET /tracks/{id}/edit/source` and
  `POST /tracks/{id}/edit/export` — audio editor: saved working edit, decoded
  original, export as a new file;
- `POST/GET /library/scan` — start a scan and read its status;
- `GET /library/folders` and `GET /library/facets` — folder tree and filter
  facets;
- `GET /review/genres` and `POST /review/genres/{id}` — review genre
  suggestions;
- `POST /analysis/genres`, `GET /analysis/genres` and
  `POST /analysis/genres/stop` — control audio analysis;
- `/cleanup/duplicates` and `/cleanup/short` — inspect cleanup candidates;
- `/cleanup/duplicates/resolve`, `/cleanup/duplicates/resolve-all`,
  `/cleanup/short/delete` and `/cleanup/delete` — move selected files to the
  Trash.

## Testing

Run the backend tests with:

```bash
pnpm test
```

The suite covers API behaviour, scanning and incremental updates, key
normalisation, folders, genre suggestions and cleanup safety rules.

## Known limitations and roadmap

- Structure detection is rule-based and tuned on house arrangements; bar 1 is
  right for ~70 % of tracks from the model alone (83 % when it is confident)
  and is corrected from the drops when they agree.
- Cues, loops and notes are quantized to the beat; cue points between beats are
  not supported.
- Ollama integration, embeddings, semantic search and AI cue suggestions are
  planned but not part of the current runtime.
- There is no direct Rekordbox synchronisation, by design: the XML export is
  imported by the user.
- Playlists and the AI set builder are planned.
- The Discogs taxonomy does not cover every DJ label, including some Afro House
  and Melodic Techno workflows; folder-based suggestions remain useful there.
- Ratings and tags are stored per database row. Identical copies are merged
  during genre review or duplicate cleanup, but they are not automatically
  shared in every operation.
- Files missing from disk are reported by the scanner and retained in the
  database; they are not automatically removed.
