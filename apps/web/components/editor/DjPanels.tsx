"use client";

import type { Anchor, Annotation, Cue, Section, SectionInput, SectionType } from "@cueflow/types";
import { Copy, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { NOTE_ICONS, type Position } from "@/components/editor/DjOverlay";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { SECTION_STYLE, positionLabel } from "@/lib/beatgrid";
import {
  CUE_COLORS,
  CUE_PRESETS,
  LOOP_LENGTHS,
  barOneAt,
  nudged,
  segmentAt,
  tapBpm,
  withBpm,
  withTempoChange,
  withoutAnchor,
  type useDjPrep,
} from "@/lib/dj-prep";
import { BEATS_PER_BAR, type TempoMap } from "@/lib/tempo";
import { cn } from "@/lib/utils";

type Prep = ReturnType<typeof useDjPrep>;

/** What every panel needs from the editor. */
export interface PanelContext {
  prep: Prep;
  tempo: TempoMap | null;
  /** Original time (s) under the playhead, and its beat-quantized position. */
  now: () => number;
  here: () => Position;
  /** Seek to an original time (mapped to the side being heard). */
  seek: (seconds: number) => void;
  /** Loop playback between two original times. */
  playLoop: (start: number, end: number) => void;
}

const label = (p: Position) => positionLabel(p.bar, p.beat);
const Heading = ({ children }: { children: React.ReactNode }) => (
  <h3 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">{children}</h3>
);
const Empty = ({ children }: { children: React.ReactNode }) => <p className="text-xs text-muted-foreground">{children}</p>;

function Swatches({ value, onChange, allowNone }: { value: string | null; onChange: (c: string | null) => void; allowNone?: boolean }) {
  return (
    <div className="flex items-center gap-0.5">
      {CUE_COLORS.map((color) => (
        <button
          type="button"
          key={color}
          aria-label={`Colour ${color}`}
          onClick={() => onChange(color)}
          className={cn("size-3.5 rounded-sm", value?.toUpperCase() === color && "ring-1 ring-foreground ring-offset-1 ring-offset-background")}
          style={{ backgroundColor: color }}
        />
      ))}
      {allowNone && (
        <button type="button" onClick={() => onChange(null)} className="ml-1 text-[10px] text-muted-foreground hover:text-foreground">
          auto
        </button>
      )}
    </div>
  );
}

/** A text field saved on blur / Enter (not on every key). */
function LazyInput({ value, onSave, placeholder, className }: { value: string; onSave: (v: string) => void; placeholder?: string; className?: string }) {
  return (
    <input
      key={value}
      defaultValue={value}
      placeholder={placeholder}
      list="cue-presets"
      maxLength={40}
      className={cn("h-6 rounded border border-border bg-background px-1.5 text-xs", className)}
      onBlur={(event) => event.target.value !== value && onSave(event.target.value)}
      onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()}
    />
  );
}

// --- Beatgrid ---

export function GridPanel({
  ctx,
  anchors,
  onChange,
  taps,
  onTap,
}: {
  ctx: PanelContext;
  anchors: Anchor[] | null;
  onChange: (a: Anchor[]) => void;
  taps: number[];
  onTap: () => void;
}) {
  if (!anchors) {
    return (
      <div className="flex items-center gap-3">
        <Empty>No beatgrid yet.</Empty>
        <Button size="sm" disabled={ctx.prep.resetGrid.isPending} onClick={() => ctx.prep.resetGrid.mutate()}>
          {ctx.prep.resetGrid.isPending ? "Analysing…" : "Detect the beatgrid"}
        </Button>
      </div>
    );
  }
  const current = () => segmentAt(anchors, ctx.now());
  const bpmBy = (delta: number) => onChange(withBpm(anchors, current(), anchors[current()].bpm + delta));
  const scale = (factor: number) => onChange(withBpm(anchors, current(), anchors[current()].bpm * factor));
  const tapped = tapBpm(taps);
  const run = (change: () => Anchor[]) => {
    try {
      onChange(change());
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs text-muted-foreground">BPM at the playhead</span>
        {[-1, -0.1, -0.01].map((d) => (
          <Button key={d} variant="outline" size="xs" onClick={() => bpmBy(d)}>
            {d}
          </Button>
        ))}
        {[0.01, 0.1, 1].map((d) => (
          <Button key={d} variant="outline" size="xs" onClick={() => bpmBy(d)}>
            +{d}
          </Button>
        ))}
        <Button variant="outline" size="xs" onClick={() => scale(2)}>
          ×2
        </Button>
        <Button variant="outline" size="xs" onClick={() => scale(0.5)}>
          ÷2
        </Button>
        <span className="mr-1 ml-3 text-xs text-muted-foreground">Move the grid</span>
        {[-0.01, -0.001, 0.001, 0.01].map((d) => (
          <Button key={d} variant="outline" size="xs" onClick={() => onChange(nudged(anchors, d))}>
            {d < 0 ? "◀ " : ""}
            {Math.abs(d * 1000)} ms{d > 0 ? " ▶" : ""}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant="outline" size="sm" title="The playhead becomes beat 1 of a bar" onClick={() => run(() => barOneAt(anchors, ctx.now()))}>
          Bar 1 here
        </Button>
        <Button
          variant="outline"
          size="sm"
          title="A new tempo section from the beat at the playhead"
          onClick={() => run(() => withTempoChange(anchors, ctx.now()))}
        >
          <Plus /> Tempo change here
        </Button>
        <Button variant="outline" size="sm" className="w-32 font-mono" title="Tap along with the beat (T)" onClick={onTap}>
          Tap (T) {tapped ? tapped.toFixed(2) : "·".repeat(Math.min(taps.length, 4))}
        </Button>
        {tapped && (
          <Button size="sm" onClick={() => onChange(withBpm(anchors, current(), tapped))}>
            Use {tapped.toFixed(2)} BPM
          </Button>
        )}
        <ConfirmButton
          variant="ghost"
          size="sm"
          confirmLabel="Replace your grid with the detected one?"
          disabled={ctx.prep.resetGrid.isPending}
          onConfirm={() => ctx.prep.resetGrid.mutate()}
        >
          {ctx.prep.resetGrid.isPending ? "Analysing…" : "Reset to detected"}
        </ConfirmButton>
      </div>
      <div className="flex flex-col gap-1">
        <Heading>Tempo sections</Heading>
        {anchors.map((anchor, i) => (
          <div key={`${i}-${anchor.time}`} className="flex items-center gap-2 font-mono text-xs tabular-nums">
            <button type="button" className="w-20 text-left hover:text-primary" onClick={() => ctx.seek(anchor.time)}>
              {anchor.time.toFixed(3)} s
            </button>
            <input
              type="number"
              step={0.01}
              min={40}
              max={250}
              defaultValue={anchor.bpm}
              key={anchor.bpm}
              aria-label="BPM"
              className="h-6 w-20 rounded border border-border bg-background px-1.5"
              onBlur={(e) => Number(e.target.value) !== anchor.bpm && onChange(withBpm(anchors, i, Number(e.target.value)))}
              onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            />
            <span className="text-muted-foreground">BPM · this beat is beat</span>
            <select
              value={anchor.beat}
              aria-label="Beat in the bar"
              className="h-6 rounded border border-border bg-background"
              onChange={(e) => onChange(anchors.map((a, k) => (k === i ? { ...a, beat: Number(e.target.value) } : a)))}
            >
              {[1, 2, 3, 4].map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
            {i > 0 && (
              <Button variant="ghost" size="icon-xs" aria-label="Remove this tempo change" onClick={() => onChange(withoutAnchor(anchors, i))}>
                <Trash2 />
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Cues and loops ---

function CueRow({ cue, ctx }: { cue: Cue; ctx: PanelContext }) {
  const edit = (changes: Parameters<Prep["editCue"]["mutate"]>[0]["changes"]) => ctx.prep.editCue.mutate({ id: cue.id, changes });
  const tempo = ctx.tempo;
  const at = tempo?.timeOf(cue.bar, cue.beat) ?? 0;
  const loop = cue.loop_beats;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-8 rounded-sm text-center font-mono font-semibold text-black" style={{ backgroundColor: cue.color ?? "#8C8C8C" }}>
        {cue.type === "HOT" ? cue.slot : loop ? "∞" : "▼"}
      </span>
      <span className="w-12 font-mono tabular-nums text-muted-foreground">{label(cue)}</span>
      <LazyInput value={cue.label ?? ""} placeholder="Name" className="w-28" onSave={(v) => edit({ label: v || null })} />
      {loop !== null && (
        <select value={loop} aria-label="Loop length" className="h-6 rounded border border-border bg-background" onChange={(e) => edit({ loop_beats: Number(e.target.value) })}>
          {[...new Set([...LOOP_LENGTHS, loop])]
            .sort((a, b) => a - b)
            .map((n) => (
              <option key={n} value={n}>
                {n === 0.5 ? "1/2" : n} beats
              </option>
            ))}
        </select>
      )}
      <Swatches value={cue.color} onChange={(color) => color && edit({ color })} />
      <Button variant="ghost" size="icon-xs" aria-label="Play from here" onClick={() => ctx.seek(at)}>
        <Play />
      </Button>
      {loop !== null && tempo && (
        <>
          <Button variant="ghost" size="xs" onClick={() => ctx.playLoop(at, tempo.timeOf(cue.bar, cue.beat + loop))}>
            Loop it
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Duplicate the loop right after itself"
            onClick={() => {
              const start = Math.ceil(cue.bar * BEATS_PER_BAR + cue.beat + loop);
              const bar = Math.floor(start / BEATS_PER_BAR);
              ctx.prep.createCue.mutate({ type: "MEMORY", bar, beat: start - bar * BEATS_PER_BAR, loop_beats: loop, label: cue.label, color: cue.color });
            }}
          >
            <Copy />
          </Button>
        </>
      )}
      <Button variant="ghost" size="icon-xs" aria-label="Delete" onClick={() => ctx.prep.deleteCue.mutate(cue.id)}>
        <Trash2 />
      </Button>
      {cue.source === "ANALYSIS" && cue.approved_by !== "USER" && <span className="text-[10px] text-muted-foreground">generated</span>}
    </div>
  );
}

export function addCue(ctx: PanelContext, type: "HOT" | "MEMORY", extra: { slot?: string; loop_beats?: number } = {}) {
  if (!ctx.tempo) return void toast.info("Detect the beatgrid first: cues are placed on beats");
  ctx.prep.createCue.mutate({ type, ...ctx.here(), ...extra });
}

export function CuePanel({ ctx }: { ctx: PanelContext }) {
  const cues = ctx.prep.cues.filter((c) => !c.loop_beats);
  const hot = new Map(ctx.prep.cues.filter((c) => c.type === "HOT").map((c) => [c.slot, c]));
  return (
    <div className="flex flex-col gap-3">
      <datalist id="cue-presets">
        {CUE_PRESETS.map((preset) => (
          <option key={preset} value={preset} />
        ))}
      </datalist>
      <div className="flex flex-wrap items-center gap-1.5">
        {"ABCDEFGH".split("").map((slot) => {
          const cue = hot.get(slot);
          return (
            <button
              type="button"
              key={slot}
              title={cue ? `${slot}${cue.label ? ` · ${cue.label}` : ""} — play from here` : `Set hot cue ${slot} at the playhead`}
              onClick={() => (cue && ctx.tempo ? ctx.seek(ctx.tempo.timeOf(cue.bar, cue.beat)) : addCue(ctx, "HOT", { slot }))}
              className={cn(
                "flex h-10 w-20 flex-col items-start justify-center rounded-md border px-2 text-left font-mono text-xs",
                cue ? "border-transparent text-black" : "border-dashed border-border text-muted-foreground hover:border-foreground",
              )}
              style={cue ? { backgroundColor: cue.color ?? "#8C8C8C" } : undefined}
            >
              <span className="font-semibold">{slot}</span>
              <span className="w-full truncate font-sans text-[10px]">{cue ? (cue.label ?? label(cue)) : "+ set here"}</span>
            </button>
          );
        })}
        <Button variant="outline" size="sm" className="ml-2" onClick={() => addCue(ctx, "HOT")}>
          <Plus /> Hot cue (C)
        </Button>
        <Button variant="outline" size="sm" onClick={() => addCue(ctx, "MEMORY")}>
          <Plus /> Memory cue (M)
        </Button>
      </div>
      <div className="flex flex-col gap-1">
        {cues.length ? cues.map((cue) => <CueRow key={cue.id} cue={cue} ctx={ctx} />) : <Empty>No cue yet: press C or M at the playhead.</Empty>}
      </div>
    </div>
  );
}

export function LoopPanel({ ctx, length, onLength }: { ctx: PanelContext; length: number; onLength: (n: number) => void }) {
  const [asHot, setAsHot] = useState(false);
  const loops = ctx.prep.cues.filter((c) => c.loop_beats);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs text-muted-foreground">Loop at the playhead</span>
        {LOOP_LENGTHS.map((n) => (
          <Button
            key={n}
            variant={n === length ? "secondary" : "outline"}
            size="sm"
            className="font-mono"
            onClick={() => {
              onLength(n);
              addCue(ctx, asHot ? "HOT" : "MEMORY", { loop_beats: n });
            }}
          >
            {n === 0.5 ? "1/2" : n}
          </Button>
        ))}
        <label className="ml-3 flex items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={asHot} onChange={(e) => setAsHot(e.target.checked)} /> hot loop (takes a slot A-H)
        </label>
        <span className="text-xs text-muted-foreground">· L adds a {length === 0.5 ? "1/2" : length}-beat loop</span>
      </div>
      <div className="flex flex-col gap-1">
        {loops.length ? (
          loops.map((cue) => <CueRow key={cue.id} cue={cue} ctx={ctx} />)
        ) : (
          <Empty>No loop yet. On the waveform: drag a loop to move it, its right edge to resize it.</Empty>
        )}
      </div>
    </div>
  );
}

// --- Sections ---

const SECTION_TYPES = Object.keys(SECTION_STYLE) as SectionType[];
const toInput = (s: Section): SectionInput => ({
  type: s.type,
  label: s.label,
  color: s.color,
  start_bar: s.start_bar,
  start_beat: s.start_beat,
  end_bar: s.end_bar,
  end_beat: s.end_beat,
});
const beatIndex = (bar: number, beat: number) => bar * BEATS_PER_BAR + beat;

/** Move the boundary between sections i-1 and i (at least one beat left on each side), or null if it can't. */
export function movedBoundary(sections: Section[], i: number, to: Position): SectionInput[] | null {
  const all = sections.map(toInput);
  const at = beatIndex(to.bar, to.beat);
  if (at <= beatIndex(all[i - 1].start_bar, all[i - 1].start_beat) || at >= beatIndex(all[i].end_bar, all[i].end_beat)) return null;
  all[i - 1] = { ...all[i - 1], end_bar: to.bar, end_beat: to.beat };
  all[i] = { ...all[i], start_bar: to.bar, start_beat: to.beat };
  return all;
}

export function SectionPanel({
  ctx,
  sections,
  selected,
  onSelect,
  endOfTrack,
}: {
  ctx: PanelContext;
  sections: Section[];
  selected: number | null;
  onSelect: (i: number | null) => void;
  endOfTrack: Position;
}) {
  const save = (next: SectionInput[]) => ctx.prep.saveSections.mutate(next);
  const all = sections.map(toInput);
  const edit = (i: number, changes: Partial<SectionInput>) => save(all.map((s, k) => (k === i ? { ...s, ...changes } : s)));
  const yours = sections.some((s) => s.source === "USER");

  const split = () => {
    const p = ctx.here();
    const at = beatIndex(p.bar, p.beat);
    const i = all.findIndex((s) => beatIndex(s.start_bar, s.start_beat) < at && at < beatIndex(s.end_bar, s.end_beat));
    if (i < 0) return void toast.info("Split: put the playhead inside a section");
    const s = all[i];
    const left = { ...s, end_bar: p.bar, end_beat: p.beat };
    const right = { ...s, label: null, start_bar: p.bar, start_beat: p.beat };
    save([...all.slice(0, i), left, right, ...all.slice(i + 1)]);
    onSelect(i + 1);
  };
  const remove = (i: number) => {
    const next = [...all];
    if (i > 0) next[i - 1] = { ...next[i - 1], end_bar: all[i].end_bar, end_beat: all[i].end_beat };
    else next[1] = { ...next[1], start_bar: all[0].start_bar, start_beat: all[0].start_beat };
    next.splice(i, 1);
    save(next);
    onSelect(null);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {sections.length ? (
          <Button variant="outline" size="sm" onClick={split}>
            Split at the playhead
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={!ctx.tempo}
            onClick={() => save([{ type: "INTRO", start_bar: 0, start_beat: 0, end_bar: endOfTrack.bar, end_beat: endOfTrack.beat }])}
          >
            <Plus /> Start sections
          </Button>
        )}
        {yours && (
          <ConfirmButton variant="ghost" size="sm" confirmLabel="Drop your sections for the detected ones?" onConfirm={() => ctx.prep.restoreSections.mutate()}>
            Restore detected sections
          </ConfirmButton>
        )}
        <span className="text-xs text-muted-foreground">
          {yours ? "Your sections (kept by re-analysis)." : sections.length ? "Detected sections: any change makes them yours." : ""} Drag a
          boundary on the waveform to move it.
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {sections.map((section, i) => (
          <div
            key={`${i}-${section.start_bar}-${section.start_beat}`}
            className={cn("flex items-center gap-2 rounded px-1 text-xs", selected === i && "bg-muted")}
            onClick={() => onSelect(i)}
          >
            <span className="w-24 font-mono tabular-nums text-muted-foreground">
              {positionLabel(section.start_bar, section.start_beat)} → {positionLabel(section.end_bar, section.end_beat)}
            </span>
            <select
              value={section.type}
              aria-label="Section type"
              className="h-6 rounded border border-border bg-background"
              onChange={(e) => edit(i, { type: e.target.value as SectionType })}
            >
              {SECTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {SECTION_STYLE[type].label}
                </option>
              ))}
            </select>
            <LazyInput value={section.label ?? ""} placeholder="Name" className="w-32" onSave={(v) => edit(i, { label: v || null })} />
            <Swatches value={section.color} allowNone onChange={(color) => edit(i, { color })} />
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Play from here"
              onClick={() => ctx.tempo && ctx.seek(ctx.tempo.timeOf(section.start_bar, section.start_beat))}
            >
              <Play />
            </Button>
            <Button variant="ghost" size="icon-xs" aria-label="Remove (merged into its neighbour)" disabled={sections.length < 2} onClick={() => remove(i)}>
              <Trash2 />
            </Button>
          </div>
        ))}
        {!sections.length && <Empty>No sections: analyse the track or start them by hand.</Empty>}
      </div>
    </div>
  );
}

// --- Notes ---

const NOTE_KINDS = Object.keys(NOTE_ICONS) as Annotation["kind"][];

export function addNote(ctx: PanelContext, kind: Annotation["kind"] = "NOTE") {
  if (!ctx.tempo) return void toast.info("Detect the beatgrid first: notes are placed on beats");
  ctx.prep.createNote.mutate({ ...ctx.here(), kind, text: "" });
}

export function NotePanel({ ctx }: { ctx: PanelContext }) {
  const notes = ctx.prep.notes;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs text-muted-foreground">Add at the playhead</span>
        {NOTE_KINDS.map((kind) => (
          <Button key={kind} variant="outline" size="sm" onClick={() => addNote(ctx, kind)}>
            {NOTE_ICONS[kind]} {kind.charAt(0) + kind.slice(1).toLowerCase()}
            {kind === "NOTE" && " (N)"}
          </Button>
        ))}
        <span className="text-xs text-muted-foreground">· notes stay in Cueflow (Rekordbox has no field for them)</span>
      </div>
      <div className="flex flex-col gap-1">
        {notes.map((note) => (
          <div key={note.id} className="flex items-center gap-2 text-xs">
            <select
              value={note.kind}
              aria-label="Kind"
              className="h-6 rounded border border-border bg-background"
              onChange={(e) => ctx.prep.editNote.mutate({ id: note.id, changes: { kind: e.target.value as Annotation["kind"] } })}
            >
              {NOTE_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {NOTE_ICONS[kind]} {kind.toLowerCase()}
                </option>
              ))}
            </select>
            <span className="w-12 font-mono tabular-nums text-muted-foreground">{label(note)}</span>
            <input
              key={note.text}
              defaultValue={note.text}
              placeholder="Note"
              maxLength={200}
              className="h-6 w-80 rounded border border-border bg-background px-1.5"
              onBlur={(e) => e.target.value !== note.text && ctx.prep.editNote.mutate({ id: note.id, changes: { text: e.target.value } })}
              onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            />
            <Button variant="ghost" size="icon-xs" aria-label="Play from here" onClick={() => ctx.tempo && ctx.seek(ctx.tempo.timeOf(note.bar, note.beat))}>
              <Play />
            </Button>
            <Button variant="ghost" size="icon-xs" aria-label="Delete" onClick={() => ctx.prep.deleteNote.mutate(note.id)}>
              <Trash2 />
            </Button>
          </div>
        ))}
        {!notes.length && <Empty>No note yet: press N at the playhead.</Empty>}
      </div>
    </div>
  );
}
