import type {
  AnalysisStatus,
  Cue,
  DuplicateKind,
  EditExportRequest,
  EditExportResult,
  EditList,
  DuplicatePage,
  ExportPreview,
  Facets,
  FolderNode,
  LiveXml,
  RekordboxImportResult,
  RekordboxImportStatus,
  RekordboxSnapshot,
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
  TrackEdit,
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

  trackEdit: (id: string) => request<TrackEdit>(`/tracks/${id}/edit`),
  saveEdit: (id: string, edit: EditList) =>
    request<TrackEdit>(`/tracks/${id}/edit`, { method: "PUT", body: JSON.stringify(edit) }),
  resetEdit: (id: string) => request<TrackEdit>(`/tracks/${id}/edit`, { method: "DELETE" }),
  /** The decoded original the editor works on (same decoder as the export). */
  editSourceUrl: (id: string) => `${API_URL}/tracks/${id}/edit/source`,
  exportEdit: (id: string, body: EditExportRequest) =>
    request<EditExportResult>(`/tracks/${id}/edit/export`, { method: "POST", body: JSON.stringify(body) }),

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
  startAnalysis: (folder?: string) =>
    request<{ started: boolean }>(`/analysis/genres?${toSearchParams({ folder })}`, { method: "POST" }),
  stopAnalysis: () => request<AnalysisStatus>("/analysis/genres/stop", { method: "POST" }),

  trackAnalysis: (id: string) => request<TrackAnalysis>(`/tracks/${id}/analysis`),
  analyseTrack: (id: string, resetGrid = false) =>
    request<TrackAnalysis>(`/tracks/${id}/analysis?reset_grid=${resetGrid}`, { method: "POST" }),
  applyAnalysis: (id: string, fields: ("bpm" | "key")[]) =>
    request<Track>(`/tracks/${id}/analysis/apply`, { method: "POST", body: JSON.stringify({ fields }) }),
  shiftDownbeat: (id: string, beats: number) =>
    request<TrackAnalysis>(`/tracks/${id}/beatgrid/shift`, { method: "POST", body: JSON.stringify({ beats }) }),
  cues: (id: string) => request<Cue[]>(`/tracks/${id}/cues`),
  approveCues: (id: string) => request<Cue[]>(`/tracks/${id}/cues/approve`, { method: "POST" }),
  regenerateCues: (id: string) => request<Cue[]>(`/tracks/${id}/cues/regenerate`, { method: "POST" }),
  deleteCue: (id: string, cueId: string) => request<Cue[]>(`/tracks/${id}/cues/${cueId}`, { method: "DELETE" }),
  exportPreview: (folder: string | undefined, approvedOnly: boolean) =>
    request<ExportPreview>(`/export/rekordbox/preview?${toSearchParams({ folder, approved_only: approvedOnly })}`),
  /** Downloads the rekordbox.xml through the browser. */
  exportRekordbox: async (body: { folder?: string; approved_only: boolean; include_beatgrid: boolean }) => {
    const response = await fetch(`${API_URL}/export/rekordbox`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail ?? `${response.status} ${response.statusText}`);
    }
    const name = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "rekordbox.xml";
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    link.click();
    URL.revokeObjectURL(url);
    return name;
  },
  audioStatus: () => request<AnalysisStatus>("/analysis/audio"),
  startAudio: (options: { folder?: string; force?: boolean } = {}) =>
    request<{ started: boolean }>(`/analysis/audio?${toSearchParams(options)}`, { method: "POST" }),
  revealFolder: (folder: string) =>
    fetch(`${API_URL}/library/reveal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder }),
    }).then(async (response) => {
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? response.statusText);
    }),
  /** Sends the collection XML itself (the API never reads a path given by the browser). */
  importRekordbox: (file: File) =>
    request<RekordboxImportResult>("/rekordbox/import", { method: "POST", body: file, headers: { "Content-Type": "application/xml" } }),
  rekordboxStatus: () => request<RekordboxImportStatus>("/rekordbox/import"),
  rekordboxSnapshot: (id: string) => request<RekordboxSnapshot | null>(`/rekordbox/tracks/${id}`),
  liveXml: () => request<LiveXml>("/export/rekordbox/live"),
  refreshLiveXml: () => request<LiveXml>("/export/rekordbox/live", { method: "POST" }),
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
