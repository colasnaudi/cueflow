// Mirrors apps/api/app/schemas.py — keep both in sync.

export type TrackStatus =
  | "NOT_ANALYZED"
  | "ANALYZING"
  | "ANALYZED"
  | "AI_REVIEW"
  | "USER_REVIEWED"
  | "EXPORTED";

export type ValueSource = "TAG" | "ANALYSIS" | "USER";

export interface Tag {
  id: string;
  name: string;
  category: string | null;
  source: string | null;
}

export interface TagCount {
  id: string;
  name: string;
  category: string | null;
  count: number;
}

export interface Track {
  id: string;
  path: string;
  filename: string;
  title: string | null;
  artist: string | null;
  album: string | null;
  label: string | null;
  genre: string | null;
  year: number | null;
  duration_ms: number | null;
  bpm: number | null;
  /** TAG (file), ANALYSIS (detected from the audio) or USER (typed in Cueflow). */
  bpm_source: ValueSource | null;
  musical_key: string | null;
  camelot_key: string | null;
  key_source: ValueSource | null;
  bitrate: number | null;
  sample_rate: number | null;
  rating: number;
  status: TrackStatus;
  file_size: number;
  tags: Tag[];
  created_at: string;
}

export interface TrackPage {
  items: Track[];
  total: number;
  limit: number;
  offset: number;
}

export interface TrackUpdate {
  rating?: number;
  genre?: string | null;
  bpm?: number | null;
  musical_key?: string | null;
}

export type SortField = "artist" | "title" | "bpm" | "key" | "genre" | "rating" | "duration" | "added";

export interface TrackQuery {
  q?: string;
  genre?: string[];
  key?: string[];
  tag?: string[];
  bpm_min?: number;
  bpm_max?: number;
  rating_min?: number;
  min_duration_ms?: number;
  dedupe?: boolean;
  folder?: string;
  sort?: SortField;
  order?: "asc" | "desc";
}

export interface Facet {
  value: string;
  count: number;
}

export interface Facets {
  genres: Facet[];
  keys: Facet[];
  bpm_min: number | null;
  bpm_max: number | null;
  total: number;
}

export interface Peaks {
  duration: number;
  peaks: number[];
}

export interface ScanStatus {
  state: "idle" | "running" | "completed" | "failed";
  running: boolean;
  error: string | null;
  root: string | null;
  total: number;
  processed: number;
  added: number;
  updated: number;
  moved: number;
  unchanged: number;
  missing: number;
  excluded: number;
  errors: string[];
  error_count: number;
  started_at: number | null;
  finished_at: number | null;
}

export interface FolderNode {
  name: string;
  path: string;
  count: number;
  children: FolderNode[];
}

export type ReviewStatus = "PENDING" | "APPROVED" | "REJECTED";
export type SuggestionSource = "FOLDER" | "AUDIO" | "FOLDER+AUDIO";

export interface GenreSuggestion {
  genre: string;
  confidence: number | null;
  source: SuggestionSource;
  rank: number;
}

export interface ReviewItem {
  track: Track;
  folder: string;
  suggestions: GenreSuggestion[];
  review: {
    status: ReviewStatus;
    chosen_genre: string | null;
    previous_genre: string | null;
    reviewed_at: string | null;
  };
}

export interface ReviewPage {
  items: ReviewItem[];
  total: number;
  counts: Record<ReviewStatus, number>;
}

/** Progress of a background job (genre analysis, audio analysis). */
export interface AnalysisStatus {
  state: "idle" | "running" | "completed" | "stopped" | "failed";
  running: boolean;
  error: string | null;
  phase: "folders" | "cues" | "audio" | null;
  /** Folder the job is limited to (null: whole library). */
  scope: string | null;
  total: number;
  processed: number;
  analyzed: number;
  current: string | null;
  errors: string[];
  error_count: number;
  started_at: number | null;
  finished_at: number | null;
}

export type DuplicateKind = "exact" | "probable";

export interface DuplicateGroup {
  /** Copies kept by default: every copy in numbered folders, Apple Music files, else the best copy. */
  keep_ids: string[];
  copies: { track: Track; folder: string; protected: boolean }[];
}

export interface DuplicatePage {
  groups: DuplicateGroup[];
  total_groups: number;
  removable_files: number;
  removable_bytes: number;
}

export interface ShortFolder {
  folder: string;
  count: number;
  bytes: number;
  sample_folder: boolean;
}

export interface ShortTracks {
  folders: ShortFolder[];
  total: number;
  max_ms: number;
}

export interface TrashResult {
  removed: number;
  freed_bytes: number;
  errors: string[];
}

export interface Beatgrid {
  bpm: number;
  /** Seconds; beat k is at first_beat + k * 60 / bpm. */
  first_beat: number;
  /** Index (0-3) of the first beat that starts a bar. */
  downbeat_offset: number;
  beats_per_bar: number;
  grid_confidence: number | null;
  downbeat_confidence: number | null;
  source: "ANALYSIS" | "USER";
}

export type SectionType = "INTRO" | "GROOVE" | "BREAK" | "BUILD" | "DROP" | "OUTRO";

/** A part of the track in musical positions: bars counted from bar 1 of the beatgrid (0-based, end exclusive). */
export interface Section {
  type: SectionType;
  start_bar: number;
  end_bar: number;
  /** Beat inside start_bar / end_bar (0-3): drops are placed to the beat. */
  start_beat: number;
  end_beat: number;
  confidence: number | null;
  source: "AUDIO" | "USER";
}

export interface TrackAnalysis {
  beatgrid: Beatgrid | null;
  musical_key: string | null;
  camelot_key: string | null;
  key_strength: number | null;
  /** One 0-1 value per bar. */
  energy_curve: number[];
  sections: Section[];
  /** Voice probability per bar. */
  vocal_curve: number[];
  /** Share of the track with a voice (0-1). */
  vocal_probability: number | null;
  analyzed_at: string | null;
}

/** A cue as a musical position (bar + beat, resolved with the beatgrid). */
export interface Cue {
  id: string;
  /** A-H for hot cues, M01... for memory cues. */
  slot: string;
  type: "HOT" | "MEMORY";
  label: string | null;
  bar: number;
  beat: number;
  color: string | null;
  confidence: number | null;
  source: "ANALYSIS" | "USER";
  approved: boolean;
  /** AUTO: approved on generation (replaced by a re-analysis); USER: validated by you (kept). */
  approved_by: "AUTO" | "USER" | null;
}

export interface ExportPreview {
  tracks: number;
  hot_cues: number;
  memory_cues: number;
  unapproved_tracks: number;
}

/** The XML file Rekordbox reads (rewritten after every audio analysis). */
export interface LiveXml {
  path: string;
  exists: boolean;
  updated_at: string | null;
  tracks: number | null;
}
