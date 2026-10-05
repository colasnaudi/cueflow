import type { EditList, EditSegment } from "@cueflow/types";

/** A range on the edited timeline, in frames (`start` < `end`). */
export interface FrameRange {
  start: number;
  end: number;
}

/** Repeated fades on the same region stack ramps; the API accepts this many per segment. */
const MAX_RAMPS = 32;
/** Normalize brings the loudest sample to this level. */
export const NORMALIZE_DBFS = -1;
export const GAIN_LIMIT_DB = 48;

export function identityEdit(sampleRate: number, frames: number): EditList {
  return { sample_rate: sampleRate, gain_db: 0, segments: [{ start: 0, end: frames, ramps: [] }] };
}

export function editLength(edit: EditList): number {
  return edit.segments.reduce((total, s) => total + s.end - s.start, 0);
}

export function isIdentity(edit: EditList, frames: number): boolean {
  const [only] = edit.segments;
  return edit.gain_db === 0 && edit.segments.length === 1 && only.start === 0 && only.end === frames && !only.ramps.length;
}

/** Output positions where two segments meet (drawn on the waveform). */
export function boundaries(edit: EditList): number[] {
  const result: number[] = [];
  let position = 0;
  for (const segment of edit.segments.slice(0, -1)) {
    position += segment.end - segment.start;
    result.push(position);
  }
  return result;
}

function splitRamp([g0, g1]: [number, number], fraction: number): [[number, number], [number, number]] {
  const middle = g0 + (g1 - g0) * fraction;
  return [
    [g0, middle],
    [middle, g1],
  ];
}

/** Cut the segment list at output frame `at` (a no-op on an existing boundary). */
function splitAt(segments: EditSegment[], at: number): EditSegment[] {
  const result: EditSegment[] = [];
  let position = 0;
  for (const segment of segments) {
    const length = segment.end - segment.start;
    if (at > position && at < position + length) {
      const offset = at - position;
      const ramps = segment.ramps.map((ramp) => splitRamp(ramp, offset / length));
      result.push(
        { start: segment.start, end: segment.start + offset, ramps: ramps.map(([left]) => left) },
        { start: segment.start + offset, end: segment.end, ramps: ramps.map(([, right]) => right) },
      );
    } else {
      result.push(segment);
    }
    position += length;
  }
  return result;
}

/** The segments before, inside and after `range`. */
function partition(edit: EditList, range: FrameRange) {
  const segments = splitAt(splitAt(edit.segments, range.start), range.end);
  const before: EditSegment[] = [];
  const inside: EditSegment[] = [];
  const after: EditSegment[] = [];
  let position = 0;
  for (const segment of segments) {
    if (position < range.start) before.push(segment);
    else if (position < range.end) inside.push(segment);
    else after.push(segment);
    position += segment.end - segment.start;
  }
  return { before, inside, after };
}

function withSegments(edit: EditList, segments: EditSegment[]): EditList {
  if (!segments.length) throw new Error("The edit cannot be empty");
  return { ...edit, segments };
}

export function copyRange(edit: EditList, range: FrameRange): EditSegment[] {
  return partition(edit, range).inside;
}

export function deleteRange(edit: EditList, range: FrameRange): EditList {
  const { before, after } = partition(edit, range);
  return withSegments(edit, [...before, ...after]);
}

export function trimTo(edit: EditList, range: FrameRange): EditList {
  return withSegments(edit, partition(edit, range).inside);
}

export function pasteAt(edit: EditList, at: number, clip: EditSegment[]): EditList {
  const { before, after } = partition(edit, { start: at, end: at });
  return withSegments(edit, [...before, ...clip, ...after]);
}

export function duplicateRange(edit: EditList, range: FrameRange): EditList {
  const { before, inside, after } = partition(edit, range);
  return withSegments(edit, [...before, ...inside, ...inside, ...after]);
}

export function splitEdit(edit: EditList, at: number): EditList {
  return withSegments(edit, splitAt(edit.segments, at));
}

/** A linear fade across `range`: in = silence to full level, out = full level to silence. */
export function fadeRange(edit: EditList, range: FrameRange, direction: "in" | "out"): EditList {
  const { before, inside, after } = partition(edit, range);
  const span = range.end - range.start;
  let position = range.start;
  const faded = inside.map((segment) => {
    if (segment.ramps.length >= MAX_RAMPS) throw new Error("Too many fades stacked on this region");
    const from = (position - range.start) / span;
    position += segment.end - segment.start;
    const to = (position - range.start) / span;
    const ramp: [number, number] = direction === "in" ? [from, to] : [1 - from, 1 - to];
    return { ...segment, ramps: [...segment.ramps, ramp] };
  });
  return withSegments(edit, [...before, ...faded, ...after]);
}

export function withGain(edit: EditList, gainDb: number): EditList {
  return { ...edit, gain_db: Math.round(Math.max(-GAIN_LIMIT_DB, Math.min(GAIN_LIMIT_DB, gainDb)) * 10) / 10 };
}

/** The gain that brings `peak` (linear, before the edit's gain) to NORMALIZE_DBFS. */
export function normalizeGain(peak: number): number | null {
  return peak > 0 ? NORMALIZE_DBFS - 20 * Math.log10(peak) : null;
}

/** Edited-timeline frame -> original frame (A/B keeps the same musical moment). */
export function toSource(edit: EditList, frame: number): number {
  let position = 0;
  for (const segment of edit.segments) {
    const length = segment.end - segment.start;
    if (frame < position + length) return segment.start + Math.max(0, frame - position);
    position += length;
  }
  return edit.segments.at(-1)!.end;
}

/** Original frame -> edited-timeline frame: the first place it is heard, else the next segment that is. */
export function toEdited(edit: EditList, frame: number): number {
  let position = 0;
  let next: number | null = null;
  for (const segment of edit.segments) {
    if (frame >= segment.start && frame < segment.end) return position + frame - segment.start;
    if (segment.start > frame && next === null) next = position;
    position += segment.end - segment.start;
  }
  return next ?? position;
}

/**
 * Render the edit (segments and fade ramps; the gain is applied live by the player) into a new buffer.
 * Mirrors `render` in apps/api/app/services/editor.py.
 */
export function renderEdit(source: AudioBuffer, edit: EditList): AudioBuffer {
  const output = new AudioBuffer({
    length: Math.max(1, editLength(edit)),
    numberOfChannels: source.numberOfChannels,
    sampleRate: source.sampleRate,
  });
  for (let channel = 0; channel < source.numberOfChannels; channel++) {
    const input = source.getChannelData(channel);
    const data = output.getChannelData(channel);
    let position = 0;
    for (const segment of edit.segments) {
      const length = segment.end - segment.start;
      data.set(input.subarray(segment.start, segment.end), position);
      for (const [g0, g1] of segment.ramps) {
        for (let i = 0; i < length; i++) data[position + i] *= g0 + ((g1 - g0) * i) / length;
      }
      position += length;
    }
  }
  return output;
}

/** Loudest absolute sample, all channels. */
export function peakOf(buffer: AudioBuffer): number {
  let peak = 0;
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const data = buffer.getChannelData(channel);
    for (let i = 0; i < data.length; i++) {
      const value = Math.abs(data[i]);
      if (value > peak) peak = value;
    }
  }
  return peak;
}

/** Frames per waveform summary block. */
export const BLOCK = 128;

/** Max absolute sample per BLOCK frames (all channels): what the waveform draws when zoomed out. */
export function summarize(buffer: AudioBuffer): Float32Array {
  const blocks = new Float32Array(Math.ceil(buffer.length / BLOCK));
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const data = buffer.getChannelData(channel);
    for (let i = 0; i < data.length; i++) {
      const value = Math.abs(data[i]);
      const block = (i / BLOCK) | 0;
      if (value > blocks[block]) blocks[block] = value;
    }
  }
  return blocks;
}

/** Every edited-timeline frame where original frame `frame` is heard (a duplicated part is heard twice). */
export function occurrences(edit: EditList, frame: number): number[] {
  const result: number[] = [];
  let position = 0;
  for (const segment of edit.segments) {
    if (frame >= segment.start && frame < segment.end) result.push(position + frame - segment.start);
    position += segment.end - segment.start;
  }
  return result;
}
