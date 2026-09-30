import type {
  AnalysisStatus,
  DuplicateKind,
  DuplicatePage,
  Facets,
  FolderNode,
  ReviewItem,
  ReviewPage,
  ReviewStatus,
  ShortTracks,
  TrashResult,
  Peaks,
  ScanStatus,
  TagCount,
  Track,
  TrackAnalysis,
  TrackPage,
  TrackQuery,
  TrackUpdate,
} from "@cueflow/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ? JSON.stringify(body.detail) : `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function toSearchParams(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) params.append(key, String(item));
  }
  return params.toString();
}

export const api = {
  tracks: (query: TrackQuery, offset = 0, limit = 100) =>
    request<TrackPage>(`/tracks?${toSearchParams({ ...query, offset, limit })}`),
  track: (id: string) => request<Track>(`/tracks/${id}`),
  updateTrack: (id: string, body: TrackUpdate) =>
    request<Track>(`/tracks/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  addTag: (id: string, name: string) =>
    request<Track>(`/tracks/${id}/tags`, { method: "POST", body: JSON.stringify({ name }) }),
  removeTag: (id: string, tagId: string) => request<Track>(`/tracks/${id}/tags/${tagId}`, { method: "DELETE" }),
  peaks: (id: string) => request<Peaks>(`/tracks/${id}/peaks`),
  audioUrl: (id: string) => `${API_URL}/tracks/${id}/audio`,
  tags: () => request<TagCount[]>("/tags"),
  facets: (minDurationMs?: number) => request<Facets>(`/library/facets?${toSearchParams({ min_duration_ms: minDurationMs })}`),
  startScan: (path?: string) =>
    request<{ root: string }>("/library/scan", { method: "POST", body: JSON.stringify({ path }) }),
  scanStatus: () => request<ScanStatus>("/library/scan"),
  folders: (minDurationMs?: number, dedupe?: boolean) =>
    request<FolderNode[]>(`/library/folders?${toSearchParams({ min_duration_ms: minDurationMs, dedupe })}`),

  reviews: (status: ReviewStatus, offset = 0, limit = 50, folder?: string) =>
    request<ReviewPage>(`/review/genres?${toSearchParams({ status, offset, limit, folder })}`),
  reviewGenre: (trackId: string, action: "approve" | "reject" | "reset", genre?: string) =>
    request<ReviewItem>(`/review/genres/${trackId}`, { method: "POST", body: JSON.stringify({ action, genre }) }),
  bulkApprove: (trackIds: string[]) =>
    request<{ approved: number }>("/review/genres/bulk-approve", { method: "POST", body: JSON.stringify({ track_ids: trackIds }) }),
  analysisStatus: () => request<AnalysisStatus>("/analysis/genres"),
  startAnalysis: () => request<{ started: boolean }>("/analysis/genres", { method: "POST" }),
  stopAnalysis: () => request<AnalysisStatus>("/analysis/genres/stop", { method: "POST" }),

  trackAnalysis: (id: string) => request<TrackAnalysis>(`/tracks/${id}/analysis`),
  analyseTrack: (id: string, resetGrid = false) =>
    request<TrackAnalysis>(`/tracks/${id}/analysis?reset_grid=${resetGrid}`, { method: "POST" }),
  applyAnalysis: (id: string, fields: ("bpm" | "key")[]) =>
    request<Track>(`/tracks/${id}/analysis/apply`, { method: "POST", body: JSON.stringify({ fields }) }),
  shiftDownbeat: (id: string, beats: number) =>
    request<TrackAnalysis>(`/tracks/${id}/beatgrid/shift`, { method: "POST", body: JSON.stringify({ beats }) }),
  audioStatus: () => request<AnalysisStatus>("/analysis/audio"),
  startAudio: () => request<{ started: boolean }>("/analysis/audio", { method: "POST" }),
  stopAudio: () => request<AnalysisStatus>("/analysis/audio/stop", { method: "POST" }),

  duplicates: (kind: DuplicateKind, offset = 0, limit = 50) =>
    request<DuplicatePage>(`/cleanup/duplicates?${toSearchParams({ kind, offset, limit })}`),
  resolveDuplicates: (keepId: string, removeIds: string[]) =>
    request<TrashResult>("/cleanup/duplicates/resolve", { method: "POST", body: JSON.stringify({ keep_id: keepId, remove_ids: removeIds }) }),
  resolveAllExact: () => request<TrashResult>("/cleanup/duplicates/resolve-all", { method: "POST" }),
  shortTracks: (maxMs: number) => request<ShortTracks>(`/cleanup/short?max_ms=${maxMs}`),
  shortTracksIn: (folder: string, maxMs: number) =>
    request<Track[]>(`/cleanup/short/tracks?${toSearchParams({ folder, max_ms: maxMs })}`),
  deleteShort: (maxMs: number, folders: string[]) =>
    request<TrashResult>("/cleanup/short/delete", { method: "POST", body: JSON.stringify({ max_ms: maxMs, folders }) }),
  deleteTracks: (trackIds: string[]) =>
    request<TrashResult>("/cleanup/delete", { method: "POST", body: JSON.stringify({ track_ids: trackIds }) }),
};
