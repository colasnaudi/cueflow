import type { Beatgrid } from "@cueflow/types";

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
