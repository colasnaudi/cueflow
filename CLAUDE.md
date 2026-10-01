# Cueflow — Claude Code Instructions

## 1. Project Overview

Cueflow is a **local-first DJ library manager** for House, Tech House and UK House libraries.

The application scans a local music collection, normalises metadata into a searchable catalogue, provides playback and waveform previews, helps organise tracks, suggests genres using local audio analysis, and provides safe duplicate and short-file cleanup workflows.

Cueflow is deliberately **non-destructive**.

Core principles:

* Never modify the metadata/tags inside source audio files unless an explicit future feature is designed and approved for that purpose.
* Never permanently delete user audio files.
* Cleanup operations move files to the macOS Trash.
* Genre suggestions must be reviewed before being applied.
* Exception decided by the user (2026-10-01): generated cue points are approved automatically
  (`AUTO_APPROVE_CUES=true`) — the DJ edits them in Rekordbox. A re-analysis replaces automatic cues, never
  cues the DJ locked/validated in Cueflow.
* AI must never directly modify Rekordbox.
* Prefer explicit user approval over automatic destructive or irreversible actions.
* Keep the application useful without cloud AI or external services.
* Audio analysis must use deterministic/audio-DSP tooling where possible.
* LLMs should interpret analysis results rather than invent precise audio timestamps.

---

# 2. Current Product Status

The current runtime implements the library-management MVP plus genre review and cleanup tools.

## Available

* Recursive music scanning
* Incremental library synchronisation
* Metadata extraction and normalisation
* SHA-256 file hashing
* Detection of moved/renamed files
* Search
* Filtering
* Sorting
* Folder browsing
* Breadcrumb navigation
* Saved library views
* Audio playback
* Persistent/shared player
* Server-computed RMS waveforms
* Manual ratings
* Manual tags
* BPM/key-compatible track matching
* Genre suggestions
* Genre review queue
* Essentia Discogs-EffNet genre analysis
* BPM analysis from raw audio (constant beatgrid fit, integer-tempo snapping)
* Beatgrid generation and phase refinement
* Downbeat detection (beat_this model, user-correctable "bar 1")
* Musical key detection (Essentia `bgate` profile)
* Per-bar energy curve
* Musical structure: INTRO / GROOVE / BREAK / BUILD / DROP / OUTRO from a kick-driven rule engine (stored in bars)
* Vocal activity per bar (Essentia voice/instrumental)
* Tag vs analysis comparison with explicit "use analysed value"
* Hot cue / memory cue generation from the sections (A START, B GROOVE, C BREAK, D DROP, E VOCAL, F DROP 2, G OUTRO), approved automatically by default
* Rekordbox XML export (cues, memory cues, beatgrid) — imported by the user with "Import To Collection"
* Live Rekordbox XML at a fixed path (`REKORDBOX_XML_PATH`, default `data/rekordbox/cueflow.xml`), rewritten
  after every audio analysis, playlists mirroring the folders — Rekordbox is pointed at it once
* Folder right-click menu: analyse audio & cues, re-analyse, analyse genres, rescan, download XML, show in Finder
* Duplicate detection
* Probable duplicate detection
* Short-track cleanup
* macOS Trash-based cleanup

## Not yet implemented

These are roadmap items, not current runtime capabilities:

* Cue editor (moving a cue on the waveform)
* Rekordbox XML import
* Ollama classification
* Ollama embeddings
* Semantic search
* AI cue suggestions
* Energy curves
* Smart Crates
* Dynamic playlists
* AI Set Builder
* Automatic transition recommendations

Do not implement roadmap features implicitly while working on unrelated tasks.

---

# 3. Product Philosophy

Cueflow is not intended to be a generic music file manager.

It is designed around a DJ workflow:

```text
Music files
    ↓
Scan
    ↓
Normalise
    ↓
Analyse
    ↓
Review
    ↓
Organise
    ↓
Prepare
    ↓
Export to DJ software
```

The long-term goal is:

> Understand the user's music library and help prepare DJ sets while keeping the user in control.

The application should progressively move from:

> Library management

towards:

> DJ library intelligence

without becoming an opaque automation system.

---

# 4. Non-Destructive Rules

These rules are mandatory.

## Audio files

Never:

* rewrite ID3 tags
* rewrite MP4 metadata
* rewrite Vorbis metadata
* overwrite source audio
* permanently delete audio
* rename or move source files without explicit user action

Database changes must not silently modify source files.

## Cleanup

Cleanup operations must:

1. Identify candidates.
2. Display what will happen.
3. Require explicit confirmation.
4. Move files to the macOS Trash.
5. Never permanently delete files.

Never introduce `rm`, permanent deletion, or equivalent behaviour for user music files.

## Metadata

Cueflow stores normalised metadata in PostgreSQL.

The database is the application's catalogue.

Source audio tags remain untouched.

## AI

AI-generated results are suggestions until explicitly approved.

AI must never:

* silently modify source audio tags
* silently change genres
* silently delete files
* directly manipulate the Rekordbox database
* invent timestamps without analysis data
* bypass user review for potentially destructive actions

---

# 5. Repository Structure

The repository is a monorepo.

```text
cueflow/
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── ...
│   │
│   └── api/
│       ├── app/
│       │   ├── routes/
│       │   ├── services/
│       │   ├── audio/
│       │   ├── models/
│       │   └── ...
│       └── ...
│
├── packages/
│   └── types/
│
├── db/
│   └── migrations/
│
├── docker/
│
├── data/
│   ├── models/
│   ├── cache/
│   └── waveforms/
│
├── scripts/
│
├── CLAUDE.md
├── README.md
├── package.json
└── pnpm-workspace.yaml
```

Keep responsibilities separated.

### `apps/web`

Frontend only.

Responsible for:

* UI
* client state
* API calls
* playback UI
* waveform rendering
* user interactions

Do not put database or filesystem logic here.

### `apps/api`

Backend and domain logic.

Responsible for:

* database access
* filesystem scanning
* audio analysis
* cleanup
* metadata extraction
* API endpoints
* background jobs

### `packages/types`

Shared TypeScript API/domain types.

Keep frontend API contracts aligned with backend responses.

### `db/migrations`

Alembic migrations only.

Never manually modify the database schema without a migration.

### `data`

Generated local data.

Never commit generated:

* waveform caches
* ML models
* analysis caches
* temporary audio data

---

# 6. Technology Stack

## Frontend

* Next.js 16
* React 19
* TypeScript
* Tailwind CSS 4
* shadcn/ui
* TanStack Query
* Zustand
* WaveSurfer.js

## Backend

* FastAPI
* Python
* Pydantic
* SQLAlchemy 2.1
* Alembic

## Database

* PostgreSQL 17
* pgvector

## Audio / metadata

* mutagen
* FFmpeg / ffprobe
* Essentia TensorFlow
* Discogs-EffNet

## Future local AI

* Ollama
* `gemma4:12b-it-qat`
* `embeddinggemma`

---

# 7. Architecture

Current architecture:

```text
┌─────────────────────────────┐
│ Next.js web app :3000       │
│                             │
│ Library · Review · Cleanup  │
│ Player · Track details      │
└──────────────┬──────────────┘
               │ REST
               ▼
┌─────────────────────────────┐
│ FastAPI API :8000           │
│                             │
│ tracks                      │
│ folders                     │
│ scan                        │
│ analysis                    │
│ review                      │
│ cleanup                     │
│ media                       │
└───────┬──────────┬──────────┘
        │          │
        ▼          ▼
 PostgreSQL    Local audio files
 + pgvector    + FFmpeg/Essentia
```

The application is local-first.

Do not introduce a cloud dependency unless explicitly requested.

---

# 8. Backend Architecture Rules

Prefer this separation:

```text
routes
  ↓
services
  ↓
repositories / SQLAlchemy
  ↓
database
```

Routes should remain thin.

Do not place large business rules directly inside FastAPI route handlers.

For example:

Bad:

```python
@router.post("/cleanup")
def cleanup(...):
    # 200 lines of filesystem logic
```

Prefer:

```python
@router.post("/cleanup")
def cleanup(...):
    return cleanup_service.resolve(...)
```

Business logic belongs in services.

---

# 9. Frontend Architecture Rules

Use:

* TanStack Query for server state
* Zustand only for local/global UI state
* React state for component-local state

Do not duplicate server state in Zustand without a strong reason.

Prefer reusable components over page-specific duplicated implementations.

Keep API calls in a dedicated API/client layer.

Avoid embedding large business rules inside React components.

---

# 10. API Rules

Current API surface includes:

```text
GET    /health

GET    /tracks
GET    /tracks/{id}
PATCH  /tracks/{id}

GET    /tracks/{id}/audio
GET    /tracks/{id}/peaks

POST   /tracks/{id}/tags
DELETE /tracks/{id}/tags/{tag_id}

POST   /library/scan
GET    /library/scan

GET    /library/folders
GET    /library/facets

GET    /review/genres
POST   /review/genres/{id}

POST   /analysis/genres
GET    /analysis/genres
POST   /analysis/genres/stop

GET    /cleanup/duplicates
POST   /cleanup/duplicates/resolve
POST   /cleanup/duplicates/resolve-all

GET    /cleanup/short
POST   /cleanup/short/delete

POST   /cleanup/delete

GET    /tracks/{id}/analysis
POST   /tracks/{id}/analysis
POST   /tracks/{id}/analysis/apply
POST   /tracks/{id}/beatgrid/shift

GET    /analysis/audio
POST   /analysis/audio
POST   /analysis/audio/stop

GET    /tracks/{id}/cues
POST   /tracks/{id}/cues/approve
POST   /tracks/{id}/cues/regenerate
DELETE /tracks/{id}/cues/{cue_id}

GET    /export/rekordbox/preview
POST   /export/rekordbox
GET    /export/rekordbox/live
POST   /export/rekordbox/live

POST   /library/reveal
```

`POST /analysis/audio` and `POST /analysis/genres` accept `folder` (and `force` for audio): the folder
right-click menu runs them on one folder and its subfolders.

When adding an endpoint:

* use Pydantic request/response models
* validate input
* return predictable response structures
* update shared TypeScript types when needed
* add tests for important behaviour
* preserve backwards compatibility where practical

---

# 11. Database Rules

Use SQLAlchemy models and Alembic migrations.

Never:

* manually mutate production/local schema without migration
* introduce duplicated sources of truth
* store derived data when it can cheaply be recomputed unless caching is intentional

Important concepts:

### Track identity

The SHA-256 hash identifies the physical file content.

The database track ID identifies the catalogue record.

Do not confuse these concepts.

### File movement

A file can move or be renamed without becoming a new track.

Use its hash to preserve catalogue history.

### Missing files

Missing files remain in the database.

Do not automatically delete missing records.

---

# 12. Scanner Rules

The scanner recursively handles:

```text
.mp3
.wav
.flac
.aiff
.aif
.m4a
```

It should:

* calculate SHA-256
* read metadata
* normalise metadata
* read duration
* read bitrate
* read sample rate
* import BPM when available
* import musical key when available
* normalise musical keys
* derive Camelot keys
* convert ID3 POPM ratings
* detect moved/renamed files
* skip unchanged files
* report scan statistics

The scanner must remain incremental.

Do not unnecessarily reanalyse unchanged files.

Use:

```text
file size
+
modification time
```

to quickly identify unchanged files.

Hash-based identity remains the source of truth when needed.

---

# 13. Metadata Normalisation

Cueflow must tolerate inconsistent DJ metadata.

Metadata fallback order should remain predictable.

For example:

```text
Artist:
tag → parsed "Artist - Title" → filename

Title:
tag → parsed "Artist - Title" → filename
```

Do not aggressively rewrite strings without a clear normalisation rule.

Preserve original source information when useful.

---

# 14. Genre Review

Genre classification is a review workflow.

Current pipeline:

```text
Folder hint
     +
Essentia Discogs-EffNet
     ↓
Genre candidates
     ↓
Confidence
     ↓
User review
     ↓
Catalogue update
```

Never silently apply model predictions.

The user must be able to:

* approve
* choose another genre
* reject
* undo

Identical copies should share reviewed genre decisions when the current cleanup/review logic says they represent the same content.

---

# 15. Audio Analysis Philosophy

Audio analysis should be deterministic whenever possible.

Use audio/DSP tooling for:

* BPM
* beat positions
* beatgrid
* downbeats
* waveform
* loudness
* spectral information
* structure
* energy curves
* vocal activity

Do not ask an LLM to determine exact audio timestamps from a raw track.

The preferred future architecture is:

```text
Audio
 ↓
DSP / Essentia
 ↓
Structured analysis
 ↓
Rule engine
 ↓
Ollama interpretation
 ↓
Validated result
```

Not:

```text
Audio
 ↓
LLM
 ↓
Random timestamps
```

---

# 16. Future Cue Engine

The future cue engine should work on musical positions rather than arbitrary timestamps.

Prefer:

```text
bar
beat
phrase
section
```

over:

```text
timestamp only
```

Example:

```json
{
  "section": "DROP",
  "bar": 41,
  "beat": 1
}
```

The engine then resolves the musical position to an exact timestamp using the beatgrid.

This is important for reliable Hot Cue generation.

---

# 17. Future AI Architecture

Ollama will be used for interpretation and semantic intelligence.

Potential responsibilities:

* genre interpretation
* subgenre classification
* mood
* DJ role
* tags
* semantic search
* transition explanation
* cue suggestions
* set-building assistance

Potential model:

```text
gemma4:12b-it-qat
```

Embeddings:

```text
embeddinggemma
```

AI responses must use structured JSON whenever possible.

Validate all model output with Pydantic before using it.

Never trust raw LLM output.

---

# 18. AI Cue Generation Rules

When cue generation is implemented, the AI should receive structured analysis.

Example:

```json
{
  "bpm": 128,
  "key": "8A",
  "energy": 0.82,
  "sections": [
    {
      "type": "INTRO",
      "start_bar": 1,
      "end_bar": 16
    },
    {
      "type": "BREAK",
      "start_bar": 33,
      "end_bar": 40
    },
    {
      "type": "DROP",
      "start_bar": 41
    }
  ]
}
```

The LLM may suggest:

```text
A = START
B = GROOVE
C = BREAK
D = DROP
E = VOCAL / SPECIAL
F = SECOND DROP
G = OUTRO
```

The rule engine validates:

* beat alignment
* bar alignment
* duplicate cues
* invalid timestamps
* section compatibility
* cue slot conflicts

AI suggestions remain reviewable.

---

# 19. Rekordbox Integration

Rekordbox integration should use **XML as the integration boundary**.

Do not manipulate the Rekordbox database directly.

Preferred architecture:

```text
Cueflow
   ↓
Validated internal representation
   ↓
Rekordbox XML
   ↓
User-controlled Rekordbox import
```

Future export may include:

* playlists
* ratings
* genres
* tags
* Hot Cues
* Memory Cues
* BPM
* key

Cueflow must never silently modify a user's Rekordbox database.

---

# 20. Playback

Current player behaviour:

```text
Space              Play / pause
Shift + Left       Previous
Shift + Right      Next
Cmd/Ctrl + K       Focus search
Double click row   Play track
```

The player should remain available while navigating the library.

Do not unnecessarily destroy/recreate the audio player when changing views.

Waveforms should remain lightweight enough for large libraries.

---

# 21. Track Matching

Current “Match playing” behaviour:

* same key
* relative key
* adjacent Camelot key
* BPM within ±3%

Future matching can add:

* energy compatibility
* structure compatibility
* vocal overlap
* intro/outro compatibility
* DJ role
* transition direction

Do not remove the existing deterministic compatibility logic just because an AI layer is introduced.

AI should complement deterministic matching.

---

# 22. Cleanup Rules

## Identical duplicates

SHA-256 identical files can be grouped safely.

The user chooses which copy to keep.

## Probable duplicates

Use conservative matching based on:

* artist
* title
* duration
* potentially future audio fingerprinting

Do not automatically delete probable duplicates.

## Preferred copies

Current behaviour:

* numbered organisation folders are preferred
* Apple Music files are protected by default

Preserve these safety rules unless explicitly changed.

## Short tracks

Current thresholds:

```text
15s
30s
60s
90s
120s
```

Protect folders that look like:

```text
TOOLS
VOCALS
VOX
SAMPLES
```

Never permanently delete files.

---

# 23. Error Handling

Errors should be:

* explicit
* actionable
* recoverable where possible

Do not silently swallow exceptions.

For background operations:

```text
pending
running
completed
failed
stopped
```

should be distinguishable.

Long-running jobs should expose progress when practical.

Users should be able to stop expensive analysis jobs safely.

---

# 24. Performance

Cueflow may handle thousands or tens of thousands of tracks.

Always consider large-library performance.

Avoid:

* loading the entire library into the browser
* giant unpaginated API responses
* recalculating audio analysis unnecessarily
* loading every waveform at once
* N+1 database queries
* blocking API requests with expensive audio processing

Prefer:

* pagination/infinite scrolling
* database filtering
* indexed columns
* background jobs
* cached analysis
* incremental scanning
* lazy loading

---

# 25. Testing

Run:

```bash
pnpm test
```

before considering backend changes complete.

Important areas requiring tests:

* scanner behaviour
* incremental sync
* moved/renamed files
* SHA-256 identity
* metadata normalisation
* key normalisation
* Camelot conversion
* folder handling
* genre review
* cleanup safety
* duplicate resolution
* short-track rules
* API validation

Any cleanup feature must have tests proving that files are not permanently deleted.

---

# 26. Development Commands

```bash
pnpm install

pnpm dev

pnpm db:up
pnpm db:down

pnpm scan
pnpm scan /path/to/music

pnpm test
```

Development requirements:

* Docker
* Node.js 22
* pnpm 10
* uv
* FFmpeg
* macOS for Trash-based cleanup

Optional:

* Ollama

---

# 27. Environment Variables

Important variables:

```text
DATABASE_URL
MUSIC_ROOT
NEXT_PUBLIC_API_URL

OLLAMA_URL
OLLAMA_LLM_MODEL
OLLAMA_EMBED_MODEL
EMBEDDING_DIM
```

Do not hardcode local machine paths.

Never hardcode:

```text
/Users/colasnaudi/...
```

inside application logic.

Use environment configuration.

---

# 28. UI / UX Principles

Cueflow is a desktop-oriented application for DJs.

The UI should prioritise:

* speed
* keyboard interaction
* information density
* clear hierarchy
* fast scanning of tracks
* minimal unnecessary dialogs
* persistent playback
* obvious destructive-action warnings

The application should feel closer to a professional DJ tool than a generic CRUD dashboard.

Avoid unnecessary decorative UI.

Prefer useful information.

For destructive actions, make the consequences obvious.

---

# 29. Visual Language

The interface should be:

* dark-first
* compact
* professional
* technical without being intimidating
* focused on tracks and metadata

Important information should be visually scannable:

```text
Artist
Title
BPM
Key
Camelot
Genre
Rating
Tags
Duration
```

Use colour meaningfully for future cue types and statuses.

Do not use excessive gradients, animations, or decorative elements that reduce information density.

---

# 30. Roadmap

## MVP 0.2 — Audio Intelligence

Priority:

1. BPM analysis
2. Beat detection
3. Beatgrid
4. Downbeat detection
5. Musical structure
6. Section detection
7. Energy curve
8. Vocal activity detection

Target architecture:

```text
Audio
 ↓
FFmpeg / Essentia
 ↓
Structured analysis
 ↓
PostgreSQL
 ↓
Waveform / timeline UI
```

---

## MVP 0.3 — DJ Intelligence

Priority:

1. Ollama integration
2. Genre/subgenre classification
3. Mood
4. Energy interpretation
5. DJ roles
6. DJ-oriented tags
7. Embeddings
8. Semantic search
9. Next-track recommendations
10. Transition compatibility explanations

---

## MVP 0.4 — Cueflow → Rekordbox

Priority:

1. Cue editor
2. Hot Cues
3. Memory Cues
4. Structure markers
5. Cue validation
6. XML import
7. XML export
8. Playlist export

Never directly edit the Rekordbox database.

---

## MVP 0.5 — Set Preparation

Potential features:

* Smart Crates
* Dynamic playlists
* Set Builder
* energy progression
* BPM progression
* key progression
* transition graph
* locked tracks
* “find next track”
* rebuild from a selected track

The user should always be able to manually edit the generated set.

---

## MVP 0.6 — Library Intelligence

Potential features:

* Library Health
* library insights
* track families / alternate versions
* global activity history
* undo system
* automatic maintenance suggestions
* improved audio fingerprinting

---

# 31. Suggested Future Concepts

These are product ideas, not current implementation requirements.

## Library Health

Example:

```text
LIBRARY HEALTH

Metadata       96%
Genres         91%
BPM            88%
Keys            84%
Ratings         63%
Duplicates      94%
DJ readiness    79%
```

The application can identify useful maintenance tasks.

---

## Energy Graph

A future track detail page may show:

```text
Energy
10 |                     ╭──────╮
 9 |                ╭────╯      ╰──╮
 8 |           ╭────╯
 7 |      ╭────╯
 6 | ╭────╯
 5 |─╯
   └──────────────────────────────
      Intro  Groove Break Drop
```

This should come from audio analysis, not arbitrary LLM output.

---

## Transition Compatibility

A future transition engine can explain:

```text
BPM             ✓
KEY             ✓
ENERGY          ✓
STRUCTURE       ✓
VOCAL CLASH     ?
```

Any compatibility score must remain explainable.

Do not create arbitrary opaque AI scores.

---

# 32. Important Engineering Principle

Do not over-engineer future features before the current workflow is stable.

Before implementing a large feature:

1. Understand the existing architecture.
2. Reuse existing services/components.
3. Check existing database models.
4. Check existing API contracts.
5. Add migrations when schema changes.
6. Add tests.
7. Preserve non-destructive behaviour.
8. Keep the change scoped.

Do not rewrite large parts of the application when a focused change is sufficient.

---

# 33. Working With Claude Code

Before changing code:

* inspect the relevant files
* understand the existing implementation
* identify existing abstractions
* avoid duplicating functionality
* respect current naming conventions

When implementing a feature:

1. Explain the intended approach internally.
2. Make the smallest coherent change.
3. Keep types consistent between frontend and backend.
4. Add/update tests.
5. Run relevant checks.
6. Fix regressions before finishing.

Do not create unnecessary files.

Do not introduce a new library when the current stack already provides the required capability.

---

# 34. Scope Discipline

Do not automatically implement every idea mentioned in this document.

The roadmap describes the direction of the product.

If a task touches a future feature that is not yet requested, do not silently expand the scope.

For example:

If asked:

> “Improve the track details page.”

Do not automatically implement:

* Ollama
* cue generation
* embeddings
* Rekordbox export
* set building

unless explicitly requested.

Prefer:

```text
requested feature
+
necessary supporting changes
```

over:

```text
requested feature
+
entire future roadmap
```

---

# 35. Security and Privacy

Cueflow is local-first.

Do not upload:

* audio files
* metadata
* library paths
* user ratings
* DJ library information

to external services unless explicitly requested.

Future AI features should use Ollama locally by default.

Be careful with filesystem paths exposed through APIs.

Never expose arbitrary filesystem access through an endpoint.

---

# 36. Definition of Done

A feature is not complete merely because it works in the happy path.

Before considering work complete:

* TypeScript compiles
* Python code is valid
* relevant backend tests pass
* API contracts are consistent
* database migrations are valid
* UI handles loading states
* UI handles errors
* destructive actions require confirmation
* filesystem operations are safe
* existing features continue to work
* no source audio metadata is modified unintentionally

For significant changes, update the README/documentation if the public behaviour changed.

---

# 37. Final Product Principle

Cueflow should always follow this principle:

> **Analyse intelligently. Suggest clearly. Let the DJ decide.**

The application should help DJs understand and prepare their music library without taking ownership of their files or workflow.

The ideal Cueflow workflow is:

```text
Scan
  ↓
Understand
  ↓
Review
  ↓
Organise
  ↓
Prepare
  ↓
Export
```

while keeping the user's original music files safe and untouched.
