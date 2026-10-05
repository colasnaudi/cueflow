"use client";

import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import { BLOCK, type FrameRange } from "@/lib/editor";

export interface WaveformHandle {
  /** Zoom by `factor` (> 1 = in) around `frame` (default: the middle of the view). */
  zoom: (factor: number, frame?: number) => void;
  /** Bring `frame` into view. */
  reveal: (frame: number) => void;
}

/** What an overlay needs to place things on the waveform. */
export interface WaveGeometry {
  /** CSS x (px, relative to the waveform box) of an edited/display frame. */
  xOf: (frame: number) => number;
  /** Display frame under a pointer event on an element inside the waveform. */
  frameAt: (event: { clientX: number; currentTarget: Element }) => number;
  width: number;
  height: number;
  /** Top of the waveform area (below the ruler). */
  top: number;
}

/** A beat line: downbeats are drawn stronger. */
export interface BeatLine {
  frame: number;
  downbeat: boolean;
}

interface EditorWaveformProps {
  ref?: React.Ref<WaveformHandle>;
  buffer: AudioBuffer;
  /** Max |sample| per BLOCK frames of `buffer`. */
  blocks: Float32Array;
  /** Linear gain applied to the drawing (the edit's gain on B, 1 on A). */
  gain: number;
  /** Selection and segment joins are only shown and editable on the edited side. */
  editable: boolean;
  selection: FrameRange | null;
  boundaries: number[];
  /** Playhead in seconds, read on every animation frame. */
  getPosition: () => number;
  playing: boolean;
  onSeek: (frame: number) => void;
  onSelect: (range: FrameRange | null) => void;
  height?: number;
  beats?: BeatLine[];
  /** Drawn over the waveform (pointer events only on what opts in). */
  overlay?: (geometry: WaveGeometry) => React.ReactNode;
}

const RULER = 18;
const OVERVIEW = 36;
const EDGE_PX = 6;
const MIN_FRAMES_PER_PX = 0.25;
const TICKS = [0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];

interface View {
  start: number;
  /** Frames per CSS pixel. */
  fpp: number;
}

function color(name: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function label(seconds: number, step: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  const decimals = step < 0.1 ? 2 : step < 1 ? 1 : 0;
  return `${minutes}:${rest.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0")}`;
}

/** Max |sample| between two frames: from the block summary when zoomed out, else from the samples. */
function amplitude(buffer: AudioBuffer, blocks: Float32Array, from: number, to: number) {
  let peak = 0;
  if (to - from >= BLOCK) {
    for (let b = Math.floor(from / BLOCK); b < Math.min(blocks.length, Math.ceil(to / BLOCK)); b++) {
      if (blocks[b] > peak) peak = blocks[b];
    }
    return peak;
  }
  const first = Math.max(0, Math.floor(from));
  const last = Math.min(buffer.length, Math.max(first + 1, Math.ceil(to)));
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const data = buffer.getChannelData(channel);
    for (let i = first; i < last; i++) {
      const value = Math.abs(data[i]);
      if (value > peak) peak = value;
    }
  }
  return peak;
}

function setupCanvas(canvas: HTMLCanvasElement, width: number, height: number) {
  const ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const ctx = canvas.getContext("2d")!;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return ctx;
}

/**
 * The editor's waveform: zoomable view with a time ruler, a whole-track overview below it, click to place the
 * playhead, drag to select, drag a selection edge to move it, double-click to select a segment.
 */
export function EditorWaveform({
  ref,
  buffer,
  blocks,
  gain,
  editable,
  selection,
  boundaries,
  getPosition,
  playing,
  onSeek,
  onSelect,
  height = 220,
  beats,
  overlay: renderOverlay,
}: EditorWaveformProps) {
  const box = useRef<HTMLDivElement>(null);
  const base = useRef<HTMLCanvasElement>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const overview = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  // Unclamped: `view` (below) is always clamped to the current width and buffer length.
  const [rawView, setRawView] = useState<View>({ start: 0, fpp: Infinity });
  const length = buffer.length;
  const rate = buffer.sampleRate;

  const clampView = useCallback(
    (next: View): View => {
      const fpp = Math.max(MIN_FRAMES_PER_PX, Math.min(next.fpp, length / Math.max(1, width)));
      const start = Math.max(0, Math.min(next.start, length - fpp * width));
      return { start, fpp };
    },
    [length, width],
  );

  // Starts fitted to the whole track; the zoom is kept (clamped) when the buffer changes length.
  const view = useMemo(() => (width ? clampView(rawView) : null), [width, rawView, clampView]);
  const setView = useCallback(
    (update: (current: View) => View) => setRawView((current) => clampView(update(clampView(current)))),
    [clampView],
  );

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      zoom: (factor, frame) =>
        setView((current) => {
          const anchor = frame ?? current.start + (current.fpp * width) / 2;
          const fpp = current.fpp / factor;
          const ratio = (anchor - current.start) / (current.fpp * width);
          return { fpp, start: anchor - ratio * fpp * width };
        }),
      reveal: (frame) =>
        setView((current) => {
          const span = current.fpp * width;
          if (frame >= current.start && frame <= current.start + span) return current;
          return { ...current, start: frame - span * 0.1 };
        }),
    }),
    [setView, width],
  );

  const waveHeight = height - RULER;

  const frameAtClient = useCallback(
    (event: { clientX: number; currentTarget: Element }) => {
      const left = event.currentTarget.closest("[data-wave-box]")?.getBoundingClientRect().left ?? 0;
      return view ? Math.max(0, Math.min(length, view.start + (event.clientX - left) * view.fpp)) : 0;
    },
    [view, length],
  );
  const geometry = useMemo<WaveGeometry | null>(
    () =>
      view && { xOf: (frame) => (frame - view.start) / view.fpp, frameAt: frameAtClient, width, height, top: RULER },
    [view, frameAtClient, width, height],
  );

  // Base layer: ruler, selection, waveform, segment joins.
  useEffect(() => {
    const canvas = base.current;
    if (!canvas || !view || !width) return;
    const ctx = setupCanvas(canvas, width, height);
    const wave = color("--wave", "#555");
    const accent = color("--wave-progress", "#f59e0b");
    const muted = color("--muted-foreground", "#888");
    const clip = color("--destructive", "#ef4444");
    const xOf = (frame: number) => (frame - view.start) / view.fpp;

    if (editable && selection) {
      const x0 = Math.max(0, xOf(selection.start));
      const x1 = Math.min(width, xOf(selection.end));
      if (x1 > x0) {
        ctx.fillStyle = accent;
        ctx.globalAlpha = 0.14;
        ctx.fillRect(x0, RULER, x1 - x0, waveHeight);
        ctx.globalAlpha = 1;
      }
    }

    const middle = RULER + waveHeight / 2;
    for (let x = 0; x < width; x++) {
      const from = view.start + x * view.fpp;
      if (from >= length) break;
      const value = amplitude(buffer, blocks, from, from + view.fpp) * gain;
      const inSelection = editable && selection && from >= selection.start && from < selection.end;
      ctx.fillStyle = value > 1 ? clip : inSelection ? accent : wave;
      const half = Math.max(0.5, (Math.min(1, value) * waveHeight) / 2 - 1);
      ctx.fillRect(x, middle - half, 1, half * 2);
    }

    if (editable) {
      ctx.strokeStyle = accent;
      ctx.setLineDash([3, 3]);
      for (const frame of boundaries) {
        const x = Math.round(xOf(frame)) + 0.5;
        if (x < 0 || x > width) continue;
        ctx.beginPath();
        ctx.moveTo(x, RULER);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    if (beats?.length) {
      const beatGap = (beats.length > 1 ? Math.abs(beats[1].frame - beats[0].frame) : Infinity) / view.fpp;
      for (const line of beats) {
        if (!line.downbeat && beatGap < 6) continue; // too dense: bars only
        if (line.downbeat && beatGap * 4 < 6) continue;
        const x = Math.round(xOf(line.frame)) + 0.5;
        if (x < 0 || x > width) continue;
        ctx.fillStyle = line.downbeat ? "rgba(255,255,255,0.35)" : "rgba(255,255,255,0.12)";
        ctx.fillRect(x - 0.5, RULER, 1, waveHeight);
      }
    }

    // Ruler: the smallest step leaving ~90 px between labels.
    const secondsPerPx = view.fpp / rate;
    const step = TICKS.find((t) => t / secondsPerPx >= 90) ?? 300;
    ctx.fillStyle = muted;
    ctx.font = "10px var(--font-geist-mono), monospace";
    ctx.textBaseline = "top";
    const first = Math.ceil(view.start / rate / step) * step;
    for (let t = first; t * rate < view.start + width * view.fpp; t += step) {
      const x = Math.round(xOf(t * rate)) + 0.5;
      ctx.fillRect(x, RULER - 5, 1, 5);
      ctx.fillText(label(t, step), x + 3, 2);
    }
    ctx.fillRect(0, RULER - 1, width, 1);
  }, [buffer, blocks, gain, editable, selection, boundaries, view, width, height, waveHeight, length, rate, beats]);

  // Overview: the whole track and the visible window.
  useEffect(() => {
    const canvas = overview.current;
    if (!canvas || !view || !width) return;
    const ctx = setupCanvas(canvas, width, OVERVIEW);
    const fpp = length / width;
    ctx.fillStyle = color("--wave", "#555");
    for (let x = 0; x < width; x++) {
      const value = Math.min(1, amplitude(buffer, blocks, x * fpp, (x + 1) * fpp) * gain);
      const half = Math.max(0.5, (value * OVERVIEW) / 2 - 1);
      ctx.fillRect(x, OVERVIEW / 2 - half, 1, half * 2);
    }
    ctx.fillStyle = color("--foreground", "#fff");
    ctx.globalAlpha = 0.12;
    ctx.fillRect(view.start / fpp, 0, Math.max(2, (view.fpp * width) / fpp), OVERVIEW);
    ctx.globalAlpha = 1;
  }, [buffer, blocks, gain, view, width, length]);

  // Playhead: its own layer, redrawn every animation frame; follows playback page by page.
  useEffect(() => {
    const canvas = overlay.current;
    if (!canvas || !view || !width) return;
    const foreground = color("--foreground", "#fff");
    let frameId = 0;
    const draw = () => {
      const ctx = setupCanvas(canvas, width, height);
      const frame = getPosition() * rate;
      if (playing && (frame < view.start || frame > view.start + view.fpp * width)) {
        setView((current) => ({ ...current, start: frame }));
        return;
      }
      const x = Math.round((frame - view.start) / view.fpp) + 0.5;
      ctx.fillStyle = foreground;
      ctx.fillRect(x - 0.5, 0, 1, height);
      ctx.beginPath();
      ctx.moveTo(x - 5, 0);
      ctx.lineTo(x + 5, 0);
      ctx.lineTo(x, 6);
      ctx.fill();
      frameId = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(frameId);
  }, [view, width, height, rate, playing, getPosition, setView]);

  // Wheel: pan (any direction), Cmd/Ctrl + wheel zooms around the pointer. Non-passive to keep the page still.
  useEffect(() => {
    const canvas = overlay.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setView((current) => {
        if (event.metaKey || event.ctrlKey) {
          const anchor = current.start + event.offsetX * current.fpp;
          const fpp = current.fpp * Math.exp(event.deltaY * 0.01);
          return { fpp, start: anchor - event.offsetX * fpp };
        }
        const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
        return { ...current, start: current.start + delta * current.fpp };
      });
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [setView]);

  const drag = useRef<{ anchor: number; x: number; moved: boolean; edge: "start" | "end" | null } | null>(null);

  const frameAt = (event: React.PointerEvent | React.MouseEvent) =>
    view ? Math.max(0, Math.min(length, Math.round(view.start + event.nativeEvent.offsetX * view.fpp))) : 0;

  const edgeAt = (event: React.PointerEvent): "start" | "end" | null => {
    if (!editable || !selection || !view) return null;
    const x = event.nativeEvent.offsetX;
    if (Math.abs(x - (selection.start - view.start) / view.fpp) <= EDGE_PX) return "start";
    if (Math.abs(x - (selection.end - view.start) / view.fpp) <= EDGE_PX) return "end";
    return null;
  };

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const edge = edgeAt(event);
    const anchor = edge === "start" ? selection!.end : edge === "end" ? selection!.start : frameAt(event);
    drag.current = { anchor, x: event.nativeEvent.offsetX, moved: false, edge };
  };

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const state = drag.current;
    if (!state) {
      event.currentTarget.style.cursor = edgeAt(event) ? "col-resize" : "text";
      return;
    }
    if (!state.edge && Math.abs(event.nativeEvent.offsetX - state.x) < 3 && !state.moved) return;
    state.moved = true;
    if (!editable) return;
    const frame = frameAt(event);
    onSelect({ start: Math.min(state.anchor, frame), end: Math.max(state.anchor, frame) });
  };

  const onPointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const state = drag.current;
    drag.current = null;
    if (!state || state.moved || state.edge) return;
    onSeek(frameAt(event));
    if (editable) onSelect(null);
  };

  /** The segment under the pointer, between two joins. */
  const onDoubleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!editable) return;
    const frame = frameAt(event);
    const joins = [0, ...boundaries, length];
    const index = joins.findIndex((join) => join > frame);
    if (index > 0) onSelect({ start: joins[index - 1], end: joins[index] });
  };

  const onOverview = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.type === "pointerdown") event.currentTarget.setPointerCapture(event.pointerId);
    else if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const center = (event.nativeEvent.offsetX / width) * length;
    setView((current) => ({ ...current, start: center - (current.fpp * width) / 2 }));
  };

  return (
    <div className="flex flex-col gap-2">
      <div ref={box} data-wave-box className="relative w-full select-none" style={{ height }}>
        <canvas ref={base} className="absolute inset-0 h-full w-full" />
        <canvas
          ref={overlay}
          className="absolute inset-0 h-full w-full touch-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onDoubleClick={onDoubleClick}
        />
        {view && renderOverlay && (
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            {geometry && renderOverlay(geometry)}
          </div>
        )}
      </div>
      <canvas
        ref={overview}
        className="w-full cursor-pointer touch-none rounded-sm bg-muted/30"
        style={{ height: OVERVIEW }}
        onPointerDown={onOverview}
        onPointerMove={onOverview}
      />
    </div>
  );
}
