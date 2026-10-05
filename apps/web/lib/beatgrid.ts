import type { Beatgrid, SectionType } from "@cueflow/types";

import { tempoOf } from "@/lib/tempo";

export function beatPeriod(grid: Beatgrid): number {
  return 60 / grid.bpm;
}

/** Time of bar 1, beat 1. */
export function firstDownbeat(grid: Beatgrid): number {
  return tempoOf(grid).timeOf(0, 0);
}

/** Start time of every bar that fits in `duration` seconds (tempo changes included). */
export function barStarts(grid: Beatgrid, duration: number): number[] {
  const tempo = tempoOf(grid);
  const starts: number[] = [];
  for (let bar = 0, t = tempo.timeOf(0); t < duration && bar < 100_000; t = tempo.timeOf(++bar)) starts.push(t);
  return starts;
}

/** Confidence below which the UI asks the DJ to check bar 1 (83 % right above it on the benchmark). */
export const TRUSTED_DOWNBEAT = 0.7;
export const TRUSTED_GRID = 0.8;

/** Seconds of a bar boundary (`bar` may be the bar count, i.e. the end of the track). */
export function barTime(starts: number[], bar: number, duration: number): number {
  return starts[bar] ?? duration;
}

/** Seconds of a musical position (bar + beat inside it). */
export function positionTime(grid: Beatgrid, starts: number[], bar: number, beat: number, duration: number): number {
  return starts[bar] === undefined ? duration : Math.min(duration, tempoOf(grid).timeOf(bar, beat));
}

/** "96" or "120.4" (bar, and beat when not on beat 1), as a DJ counts. */
export function positionLabel(bar: number, beat: number): string {
  return beat ? `${bar + 1}.${beat + 1}` : String(bar + 1);
}

export const SECTION_STYLE: Record<SectionType, { label: string; className: string }> = {
  INTRO: { label: "Intro", className: "bg-slate-400/25 text-slate-200" },
  GROOVE: { label: "Groove", className: "bg-sky-500/25 text-sky-200" },
  BREAK: { label: "Break", className: "bg-violet-500/30 text-violet-200" },
  BUILD: { label: "Build", className: "bg-amber-500/30 text-amber-200" },
  DROP: { label: "Drop", className: "bg-rose-500/30 text-rose-200" },
  OUTRO: { label: "Outro", className: "bg-slate-400/25 text-slate-200" },
  VERSE: { label: "Verse", className: "bg-cyan-500/25 text-cyan-200" },
  CHORUS: { label: "Chorus", className: "bg-yellow-500/25 text-yellow-200" },
  BRIDGE: { label: "Bridge", className: "bg-fuchsia-500/25 text-fuchsia-200" },
  CUSTOM: { label: "Custom", className: "bg-emerald-500/25 text-emerald-200" },
};
