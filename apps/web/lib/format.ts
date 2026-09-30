export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "–";
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function formatTime(seconds: number): string {
  return formatDuration(seconds * 1000);
}

export function formatBpm(bpm: number | null | undefined): string {
  if (bpm == null) return "–";
  return Number.isInteger(bpm) ? String(bpm) : bpm.toFixed(1);
}

export function trackTitle(track: { title: string | null; filename: string }): string {
  return track.title ?? track.filename;
}

/** Camelot wheel colour: each number gets its own hue, minor (A) keys are darker than major (B). */
export function camelotColor(camelot: string | null | undefined): string | undefined {
  const match = camelot?.match(/^(\d{1,2})([AB])$/);
  if (!match) return undefined;
  const hue = ((Number(match[1]) - 1) * 30 + 150) % 360;
  return match[2] === "A" ? `oklch(0.72 0.14 ${hue})` : `oklch(0.84 0.12 ${hue})`;
}

/** Harmonically compatible Camelot keys: same key, ±1 on the wheel, and the relative major/minor. */
export function compatibleKeys(camelot: string): string[] {
  const match = camelot.match(/^(\d{1,2})([AB])$/);
  if (!match) return [];
  const n = Number(match[1]);
  const letter = match[2];
  const wrap = (x: number) => ((x - 1 + 12) % 12) + 1;
  return [`${n}${letter}`, `${wrap(n - 1)}${letter}`, `${wrap(n + 1)}${letter}`, `${n}${letter === "A" ? "B" : "A"}`];
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
  return `${Math.round(bytes / 1e3)} KB`;
}
