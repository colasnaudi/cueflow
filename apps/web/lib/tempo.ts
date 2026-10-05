import type { Anchor, Beatgrid } from "@cueflow/types";

/**
 * Tempo map: musical positions (bar, beat) <-> seconds for constant and variable grids. Mirrors
 * apps/api/app/services/tempo.py: bar 0 starts on the first downbeat at or after the first anchor.
 */
export const BEATS_PER_BAR = 4;

export function anchorsOf(grid: Beatgrid): Anchor[] {
  if (grid.anchors?.length) return grid.anchors;
  const beat = ((BEATS_PER_BAR - grid.downbeat_offset) % BEATS_PER_BAR) + 1;
  return [{ time: grid.first_beat, bpm: grid.bpm, beat }];
}

const mod = (value: number, n: number) => ((value % n) + n) % n;

export class TempoMap {
  readonly anchors: Anchor[];
  private starts: number[];

  constructor(anchors: Anchor[]) {
    if (!anchors.length) throw new Error("a tempo map needs at least one anchor");
    this.anchors = [...anchors].sort((a, b) => a.time - b.time);
    this.starts = [-mod(BEATS_PER_BAR + 1 - this.anchors[0].beat, BEATS_PER_BAR)];
    for (let i = 1; i < this.anchors.length; i++) {
      const previous = this.anchors[i - 1];
      const anchor = this.anchors[i];
      let start = this.starts[i - 1] + Math.round(((anchor.time - previous.time) * previous.bpm) / 60);
      start += mod(anchor.beat - 1 - start, BEATS_PER_BAR); // its own Battito sets the bar phase
      this.starts.push(start);
    }
  }

  private segmentForIndex(index: number) {
    let segment = 0;
    this.starts.forEach((start, i) => index >= start && (segment = i));
    return segment;
  }

  private segmentForTime(time: number) {
    let segment = 0;
    this.anchors.forEach((anchor, i) => time >= anchor.time && (segment = i));
    return segment;
  }

  /** Seconds of a (fractional) global beat index (0 = bar 1, beat 1). */
  timeOfIndex(index: number): number {
    const segment = this.segmentForIndex(index);
    const anchor = this.anchors[segment];
    return anchor.time + ((index - this.starts[segment]) * 60) / anchor.bpm;
  }

  indexOf(time: number): number {
    const segment = this.segmentForTime(time);
    const anchor = this.anchors[segment];
    return this.starts[segment] + ((time - anchor.time) * anchor.bpm) / 60;
  }

  timeOf(bar: number, beat = 0): number {
    return this.timeOfIndex(bar * BEATS_PER_BAR + beat);
  }

  /** Nearest beat (or nearest bar with `unit` = "bar"), as { bar, beat }. */
  positionOf(time: number, unit: "beat" | "bar" = "beat"): { bar: number; beat: number } {
    const step = unit === "bar" ? BEATS_PER_BAR : 1;
    const index = Math.round(this.indexOf(time) / step) * step;
    return { bar: Math.floor(index / BEATS_PER_BAR), beat: mod(index, BEATS_PER_BAR) };
  }

  bpmAt(time: number): number {
    return this.anchors[this.segmentForTime(time)].bpm;
  }

  /** Every beat between two times: { time, index } (index % 4 === 0 on a downbeat). */
  beatsBetween(from: number, to: number): { time: number; index: number }[] {
    const beats = [];
    for (let index = Math.ceil(this.indexOf(Math.max(0, from))); ; index++) {
      const time = this.timeOfIndex(index);
      if (time > to || beats.length > 100_000) break;
      if (time >= 0) beats.push({ time, index });
    }
    return beats;
  }
}

const cache = new WeakMap<Beatgrid, TempoMap>();

export function tempoOf(grid: Beatgrid): TempoMap {
  let map = cache.get(grid);
  if (!map) cache.set(grid, (map = new TempoMap(anchorsOf(grid))));
  return map;
}
