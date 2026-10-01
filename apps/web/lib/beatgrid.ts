import type { Beatgrid, SectionType } from "@cueflow/types";

export function beatPeriod(grid: Beatgrid): number {
  return 60 / grid.bpm;
}

/** Time of bar 1, beat 1. */
export function firstDownbeat(grid: Beatgrid): number {
  return grid.first_beat + grid.downbeat_offset * beatPeriod(grid);
}

/** Start time of every bar that fits in `duration` seconds. */
export function barStarts(grid: Beatgrid, duration: number): number[] {
  const bar = beatPeriod(grid) * grid.beats_per_bar;
  const starts: number[] = [];
  for (let t = firstDownbeat(grid); t < duration; t += bar) starts.push(t);
  return starts;
}

/** Confidence below which the UI asks the DJ to check bar 1 (83 % right above it on the benchmark). */
export const TRUSTED_DOWNBEAT = 0.7;
export const TRUSTED_GRID = 0.8;

/** Seconds of a bar boundary (`bar` may be the bar count, i.e. the end of the track). */
export function barTime(starts: number[], bar: number, duration: number): number {
  return starts[bar] ?? duration;
}

export const SECTION_STYLE: Record<SectionType, { label: string; className: string }> = {
  INTRO: { label: "Intro", className: "bg-slate-400/25 text-slate-200" },
  GROOVE: { label: "Groove", className: "bg-sky-500/25 text-sky-200" },
  BREAK: { label: "Break", className: "bg-violet-500/30 text-violet-200" },
  BUILD: { label: "Build", className: "bg-amber-500/30 text-amber-200" },
  DROP: { label: "Drop", className: "bg-rose-500/30 text-rose-200" },
  OUTRO: { label: "Outro", className: "bg-slate-400/25 text-slate-200" },
};
