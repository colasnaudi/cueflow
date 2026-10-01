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
| Cue editor and Rekordbox XML import/export | Planned for MVP 0.4 |
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

BPM and key are only written to the catalogue when the file tags have none; a
differing tag is shown on the track page and replaced only on request.
Analysis takes about 7-12 s per track (`ANALYSIS_WORKERS` processes in
parallel).

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

## Commands

| Command | Description |
| --- | --- |
| `pnpm dev` | Start PostgreSQL, migrations, API and web with reload |
| `pnpm db:up` | Start PostgreSQL and wait until it is healthy |
| `pnpm db:down` | Stop PostgreSQL while keeping its Docker volume |
| `pnpm scan` | Scan `MUSIC_ROOT` from the command line |
| `pnpm scan /path/to/music` | Scan a specific folder |
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
- Hot cues, memory cues, structure markers and waveform cue editing are not
  implemented yet.
- Ollama integration, embeddings, semantic search and AI cue suggestions are
  planned but not part of the current runtime.
- Rekordbox XML import/export is planned; there is currently no direct
  Rekordbox synchronisation.
- Playlists and the AI set builder are planned.
- The Discogs taxonomy does not cover every DJ label, including some Afro House
  and Melodic Techno workflows; folder-based suggestions remain useful there.
- Ratings and tags are stored per database row. Identical copies are merged
  during genre review or duplicate cleanup, but they are not automatically
  shared in every operation.
- Files missing from disk are reported by the scanner and retained in the
  database; they are not automatically removed.
