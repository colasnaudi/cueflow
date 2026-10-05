"use client";

import type { Annotation, Cue, Section } from "@cueflow/types";
import { useRef, useState } from "react";

import type { WaveGeometry } from "@/components/editor/EditorWaveform";
import { SECTION_STYLE } from "@/lib/beatgrid";
import { cn } from "@/lib/utils";
import { BEATS_PER_BAR, type TempoMap } from "@/lib/tempo";

export const NOTE_ICONS: Record<Annotation["kind"], string> = {
  NOTE: "📝",
  DROP: "🔴",
  VOCAL: "🗣",
  WARNING: "⚠️",
  FIRE: "🔥",
};

/** A musical position (beat-quantized). */
export interface Position {
  bar: number;
  beat: number;
}

interface DjOverlayProps {
  geometry: WaveGeometry;
  tempo: TempoMap;
  rate: number;
  /** Display frames (one per place it is heard) of an original time in seconds. */
  display: (seconds: number) => number[];
  /** Original time (seconds) of a display frame. */
  toSeconds: (frame: number) => number;
  cues: Cue[];
  notes: Annotation[];
  sections: Section[];
  selectedSection: number | null;
  onMoveCue: (cue: Cue, to: Position) => void;
  onResizeLoop: (cue: Cue, from: Position, beats: number) => void;
  onMoveNote: (note: Annotation, to: Position) => void;
  /** Move the boundary between sections index-1 and index. */
  onMoveBoundary: (index: number, to: Position) => void;
  onSelectSection: (index: number) => void;
  onSeek: (frame: number) => void;
}

const SECTION_LANE = 16;
const LANE_GAP = 2;

/**
 * Drag helper: follows the pointer (preview) and reports the frame on release. A click without movement calls
 * `onClick` instead.
 */
function useDrag(geometry: WaveGeometry, onDrop: (frame: number) => void, onClick?: () => void) {
  const [preview, setPreview] = useState<number | null>(null);
  const start = useRef<{ x: number; moved: boolean } | null>(null);
  return {
    preview,
    handlers: {
      onPointerDown: (event: React.PointerEvent) => {
        if (event.button !== 0) return;
        event.stopPropagation();
        event.currentTarget.setPointerCapture(event.pointerId);
        start.current = { x: event.clientX, moved: false };
      },
      onPointerMove: (event: React.PointerEvent) => {
        if (!start.current) return;
        if (!start.current.moved && Math.abs(event.clientX - start.current.x) < 3) return;
        start.current.moved = true;
        setPreview(geometry.frameAt(event));
      },
      onPointerUp: (event: React.PointerEvent) => {
        const state = start.current;
        start.current = null;
        setPreview(null);
        if (state?.moved) onDrop(geometry.frameAt(event));
        else onClick?.();
      },
    },
  };
}

function CueFlag({ cue, x, props }: { cue: Cue; x: number; props: DjOverlayProps }) {
  const { geometry, tempo, toSeconds, onMoveCue, onSeek } = props;
  const drag = useDrag(
    geometry,
    (frame) => onMoveCue(cue, tempo.positionOf(toSeconds(frame))),
    () => onSeek(x),
  );
  const left = drag.preview !== null ? geometry.xOf(drag.preview) : geometry.xOf(x);
  const hot = cue.type === "HOT";
  const color = cue.color ?? "#8C8C8C";
  const top = geometry.top + SECTION_LANE + LANE_GAP;
  return (
    <>
      <div className="absolute w-px opacity-70" style={{ left, top, bottom: 0, backgroundColor: color }} />
      <button
        type="button"
        title={`${hot ? `Hot cue ${cue.slot}` : "Memory cue"}${cue.label ? ` · ${cue.label}` : ""} — drag to move`}
        className={cn(
          "pointer-events-auto absolute flex h-4 cursor-grab items-center rounded-r-sm px-1 font-mono text-[10px] leading-none font-semibold text-black active:cursor-grabbing",
          !hot && "rounded-sm opacity-80",
        )}
        style={{ left, top: hot ? top : geometry.height - 18, backgroundColor: color }}
        {...drag.handlers}
      >
        {hot ? cue.slot : "▼"}
        {cue.label && <span className="ml-1 max-w-24 truncate font-sans font-medium">{cue.label}</span>}
      </button>
    </>
  );
}

function LoopBand({ cue, start, props }: { cue: Cue; start: number; props: DjOverlayProps }) {
  const { geometry, tempo, toSeconds, rate, onResizeLoop, onMoveCue } = props;
  const beats = cue.loop_beats ?? 4;
  const startIndex = cue.bar * BEATS_PER_BAR + cue.beat;
  const lengthFrames = (tempo.timeOfIndex(startIndex + beats) - tempo.timeOfIndex(startIndex)) * rate;
  const resize = useDrag(geometry, (frame) => {
    const end = tempo.indexOf(toSeconds(frame));
    onResizeLoop(cue, { bar: cue.bar, beat: cue.beat }, Math.max(0.5, Math.round((end - startIndex) * 2) / 2));
  });
  const move = useDrag(geometry, (frame) => onMoveCue(cue, tempo.positionOf(toSeconds(frame))));
  const left = geometry.xOf(move.preview ?? start);
  const pxPerFrame = geometry.xOf(1) - geometry.xOf(0);
  const right = resize.preview !== null ? geometry.xOf(resize.preview) : left + lengthFrames * pxPerFrame;
  const color = cue.color ?? "#10B1C8";
  return (
    <div
      className="pointer-events-auto absolute flex cursor-grab items-center rounded-sm border text-[10px] font-medium active:cursor-grabbing"
      style={{
        left,
        width: Math.max(4, right - left),
        bottom: 20,
        height: 14,
        borderColor: color,
        backgroundColor: `${color}40`,
      }}
      title={`Loop ${beats} beats${cue.label ? ` · ${cue.label}` : ""} — drag to move, drag the right edge to resize`}
      {...move.handlers}
    >
      <span className="truncate px-1">{cue.type === "HOT" ? cue.slot : "∞"} {beats}</span>
      <span
        className="absolute top-0 right-0 h-full w-1.5 cursor-ew-resize"
        style={{ backgroundColor: color }}
        {...resize.handlers}
      />
    </div>
  );
}

function NoteMark({ note, x, props }: { note: Annotation; x: number; props: DjOverlayProps }) {
  const { geometry, tempo, toSeconds, onMoveNote, onSeek } = props;
  const drag = useDrag(geometry, (frame) => onMoveNote(note, tempo.positionOf(toSeconds(frame))), () => onSeek(x));
  const left = geometry.xOf(drag.preview ?? x);
  return (
    <button
      type="button"
      title={`${note.text || note.kind} — drag to move`}
      className="pointer-events-auto absolute flex cursor-grab items-center gap-0.5 text-xs leading-none active:cursor-grabbing"
      style={{ left: left - 6, bottom: 38 }}
      {...drag.handlers}
    >
      {NOTE_ICONS[note.kind]}
      {note.text && <span className="max-w-28 truncate rounded bg-background/70 px-1 text-[10px]">{note.text}</span>}
    </button>
  );
}

function Boundary({ index, x, props }: { index: number; x: number; props: DjOverlayProps }) {
  const { geometry, tempo, toSeconds, onMoveBoundary } = props;
  const drag = useDrag(geometry, (frame) => onMoveBoundary(index, tempo.positionOf(toSeconds(frame))));
  return (
    <span
      title="Drag to move the section boundary"
      className="pointer-events-auto absolute w-2 cursor-ew-resize bg-foreground/0 hover:bg-foreground/40"
      style={{ left: geometry.xOf(drag.preview ?? x) - 4, top: geometry.top, height: SECTION_LANE }}
      {...drag.handlers}
    />
  );
}

/** Sections, cues, loops and notes over the editor waveform. Positions snap to the beat. */
export function DjOverlay(props: DjOverlayProps) {
  const { geometry, tempo, rate, display, cues, notes, sections, selectedSection, onSelectSection } = props;
  const visible = (frame: number) => {
    const x = geometry.xOf(frame);
    return x > -200 && x < geometry.width + 200;
  };
  const framesOf = (bar: number, beat: number) => display(tempo.timeOf(bar, beat)).filter(visible);

  return (
    <>
      {sections.map((section, i) => {
        const starts = display(tempo.timeOf(section.start_bar, section.start_beat));
        const ends = display(tempo.timeOf(section.end_bar, section.end_beat) - 1 / rate);
        return starts.map((start, k) => {
          const end = (ends[k] ?? start) + 1;
          const style = SECTION_STYLE[section.type];
          return (
            <button
              type="button"
              key={`${i}-${k}`}
              onClick={() => onSelectSection(i)}
              className={cn(
                "pointer-events-auto absolute truncate rounded-sm px-1 text-left text-[10px] leading-4 font-medium",
                style.className,
                selectedSection === i && "ring-1 ring-foreground",
              )}
              style={{
                left: geometry.xOf(start),
                width: Math.max(2, geometry.xOf(end) - geometry.xOf(start) - 1),
                top: geometry.top,
                height: SECTION_LANE,
                ...(section.color ? { backgroundColor: `${section.color}55` } : {}),
              }}
              title={`${section.label ?? style.label} — click to edit`}
            >
              {section.label ?? style.label}
            </button>
          );
        });
      })}
      {sections.slice(1).map((section, i) =>
        framesOf(section.start_bar, section.start_beat).map((x) => <Boundary key={`b${i}-${x}`} index={i + 1} x={x} props={props} />),
      )}
      {cues
        .filter((c) => c.loop_beats)
        .flatMap((cue) => framesOf(cue.bar, cue.beat).map((x) => <LoopBand key={`${cue.id}-${x}`} cue={cue} start={x} props={props} />))}
      {cues
        .filter((c) => !c.loop_beats)
        .flatMap((cue) => framesOf(cue.bar, cue.beat).map((x) => <CueFlag key={`${cue.id}-${x}`} cue={cue} x={x} props={props} />))}
      {notes.flatMap((note) => framesOf(note.bar, note.beat).map((x) => <NoteMark key={`${note.id}-${x}`} note={note} x={x} props={props} />))}
    </>
  );
}
