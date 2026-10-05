"use client";

import type { EditExportFormat, EditExportRequest, Track } from "@cueflow/types";
import {
  ArrowLeft,
  ClipboardPaste,
  Copy,
  CopyPlus,
  Download,
  Minus,
  Pause,
  Play,
  Plus,
  Redo2,
  Repeat,
  Save,
  Scissors,
  SkipBack,
  Square,
  SquareSplitHorizontal,
  Trash2,
  Undo2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { EditorWaveform, type WaveformHandle } from "@/components/editor/EditorWaveform";
import { KeyBadge } from "@/components/library/KeyBadge";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { api } from "@/lib/api";
import {
  boundaries as segmentJoins,
  copyRange,
  deleteRange,
  duplicateRange,
  editLength,
  fadeRange,
  identityEdit,
  isIdentity,
  normalizeGain,
  pasteAt,
  peakOf,
  renderEdit,
  splitEdit,
  summarize,
  toEdited,
  toSource,
  trimTo,
  withGain,
} from "@/lib/editor";
import type { EditorEngine } from "@/lib/editor-audio";
import { useEditor } from "@/lib/editor-store";
import { formatBpm, trackTitle } from "@/lib/format";
import { cn } from "@/lib/utils";

const QUALITIES: Record<EditExportFormat, EditExportRequest["quality"][]> = { wav: [16, 24], mp3: [320, 256, 192] };
const GAIN_SLIDER_DB = 12;

function isTyping(target: EventTarget | null) {
  return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
}

/** m:ss.mmm */
function clock(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(3).padStart(6, "0")}`;
}

function Clock({ engine }: { engine: EditorEngine }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      if (ref.current) ref.current.textContent = clock(engine.position);
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [engine]);
  return <span ref={ref} className="w-24 font-mono text-sm tabular-nums" />;
}

function Tool({ label, shortcut, ...props }: React.ComponentProps<typeof Button> & { label: string; shortcut?: string }) {
  return (
    <Button variant="outline" size="sm" title={shortcut ? `${label} (${shortcut})` : label} {...props}>
      {props.children}
      {label}
    </Button>
  );
}

interface EditorProps {
  track: Track;
  original: AudioBuffer;
  engine: EditorEngine;
}

/** The loaded editor: waveform, edit tools, transport. All edits go through the store (undo/redo). */
export function Editor({ track, original, engine }: EditorProps) {
  const router = useRouter();
  const { edit, past, future, selection, clipboard, savedJson, apply, undo, redo, select, setClipboard, markSaved } =
    useEditor();
  const state = useSyncExternalStore(engine.subscribe, () => engine.state, () => engine.state);
  const waveform = useRef<WaveformHandle>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [format, setFormat] = useState<EditExportFormat>("wav");
  const [quality, setQuality] = useState<EditExportRequest["quality"]>(16);
  const [busy, setBusy] = useState<"save" | "export" | null>(null);

  const rate = original.sampleRate;
  const segments = edit?.segments;
  // The gain is applied live by the engine: only the segments (cuts, fades) need a new render.
  const rendered = useMemo(() => {
    if (!edit) return null;
    const buffer = renderEdit(original, edit);
    return { buffer, blocks: summarize(buffer), peak: peakOf(buffer) };
  }, [original, segments]); // eslint-disable-line react-hooks/exhaustive-deps
  const originalBlocks = useMemo(() => summarize(original), [original]);

  useEffect(() => {
    if (rendered) engine.setEdited(rendered.buffer);
  }, [engine, rendered]);
  useEffect(() => {
    if (edit) engine.setGainDb(edit.gain_db);
  }, [engine, edit]);

  const dirty = !!edit && JSON.stringify(edit) !== (savedJson ?? JSON.stringify(identityEdit(rate, original.length)));
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const editing = state.side === "B";
  const playhead = useCallback(() => Math.round(engine.position * rate), [engine, rate]);
  const getPosition = useCallback(() => engine.position, [engine]);

  /** Run an edit operation on the edited side; errors (empty edit, too many fades) become toasts. */
  const run = (operation: () => void) => {
    if (!edit || !editing) return;
    try {
      operation();
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  const needSelection = (name: string) => {
    if (!selection) toast.info(`${name}: select a region first`);
    return selection;
  };

  const actions = {
    cut: () =>
      run(() => {
        const range = needSelection("Cut");
        if (!range || !edit) return;
        setClipboard(copyRange(edit, range));
        apply(deleteRange(edit, range));
        select(null);
        engine.seek(range.start / rate);
      }),
    copy: () =>
      run(() => {
        const range = needSelection("Copy");
        if (!range || !edit) return;
        setClipboard(copyRange(edit, range));
        toast.success(`Copied ${clock((range.end - range.start) / rate)}`);
      }),
    paste: () =>
      run(() => {
        if (!edit) return;
        if (!clipboard) return void toast.info("Paste: copy or cut a region first");
        const at = playhead();
        const length = clipboard.reduce((total, s) => total + s.end - s.start, 0);
        apply(pasteAt(edit, at, clipboard));
        select({ start: at, end: at + length });
      }),
    duplicate: () =>
      run(() => {
        const range = needSelection("Duplicate");
        if (!range || !edit) return;
        apply(duplicateRange(edit, range));
        select({ start: range.end, end: range.end + range.end - range.start });
      }),
    remove: () =>
      run(() => {
        const range = needSelection("Delete");
        if (!range || !edit) return;
        apply(deleteRange(edit, range));
        select(null);
        engine.seek(range.start / rate);
      }),
    trim: () =>
      run(() => {
        const range = needSelection("Trim");
        if (!range || !edit) return;
        apply(trimTo(edit, range));
        select(null);
        engine.seek(0);
      }),
    split: () =>
      run(() => {
        if (!edit) return;
        const next = splitEdit(edit, playhead());
        if (next.segments.length !== edit.segments.length) apply(next);
      }),
    fade: (direction: "in" | "out") =>
      run(() => {
        const range = needSelection(direction === "in" ? "Fade in" : "Fade out");
        if (!range || !edit) return;
        apply(fadeRange(edit, range, direction));
      }),
    normalize: () =>
      run(() => {
        if (!edit || !rendered) return;
        const gain = normalizeGain(rendered.peak);
        if (gain === null) return void toast.info("Normalize: the edit is silent");
        apply(withGain(edit, gain));
      }),
    gain: (db: number) => run(() => edit && apply(withGain(edit, db), "gain")),
  };

  const transport = {
    toggle: () => (state.playing ? engine.pause() : engine.play()),
    stop: () => {
      engine.pause();
      engine.seek(editing && selection ? selection.start / rate : 0);
    },
    home: () => {
      engine.seek(0);
      waveform.current?.reveal(0);
    },
    nudge: (seconds: number) => {
      engine.seek(engine.position + seconds);
      waveform.current?.reveal(playhead());
    },
    playSelection: () => {
      if (!editing || !selection) return void toast.info("Select a region to play it");
      engine.play(selection.start / rate, { start: selection.start / rate, end: selection.end / rate });
    },
    loop: () => {
      engine.setLoop(!state.loop);
      if (state.playing && editing && selection) {
        engine.play(engine.position, { start: selection.start / rate, end: selection.end / rate });
      }
    },
    /** A/B at the same musical moment: the position is mapped through the edit list. */
    ab: () => {
      if (!edit) return;
      const frame = playhead();
      const mapped = editing ? toSource(edit, frame) : toEdited(edit, frame);
      engine.setSide(editing ? "A" : "B", mapped / rate);
    },
  };

  const save = async () => {
    if (!edit) return;
    setBusy("save");
    try {
      if (isIdentity(edit, original.length)) {
        await api.resetEdit(track.id);
        markSaved(null);
      } else {
        await api.saveEdit(track.id, edit);
        markSaved(edit);
      }
      toast.success("Edit saved");
    } catch (error) {
      toast.error(`Save failed: ${(error as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    try {
      await api.resetEdit(track.id);
      apply(identityEdit(rate, original.length));
      markSaved(null);
      select(null);
      toast.success("Edit reset to the original");
    } catch (error) {
      toast.error(`Reset failed: ${(error as Error).message}`);
    }
  };

  const exportFile = async () => {
    if (!edit) return;
    setBusy("export");
    try {
      const result = await api.exportEdit(track.id, { edit, format, quality });
      setExportOpen(false);
      toast.success(`Exported ${result.filename}`, { description: result.path, duration: 10_000 });
    } catch (error) {
      toast.error(`Export failed: ${(error as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  // Keyboard: handled here while the editor is open (the global player bar ignores keys on this page).
  const keys = {
    actions,
    transport,
    undo,
    redo,
    save,
    select,
    length: rendered?.buffer.length ?? 0,
    zoom: (factor: number) => waveform.current?.zoom(factor, playhead()),
  };
  const handlers = useRef(keys);
  useEffect(() => {
    handlers.current = keys;
  });
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target)) return;
      const h = handlers.current;
      const step = event.altKey ? 0.01 : event.shiftKey ? 1 : 0.1;
      const commands: Record<string, () => void> = {
        x: h.actions.cut,
        c: h.actions.copy,
        v: h.actions.paste,
        d: h.actions.duplicate,
        a: () => h.select({ start: 0, end: h.length }),
        z: event.shiftKey ? h.redo : h.undo,
        y: h.redo,
        s: () => void h.save(),
      };
      const plain: Record<string, () => void> = {
        " ": h.transport.toggle,
        home: h.transport.home,
        arrowleft: () => h.transport.nudge(-step),
        arrowright: () => h.transport.nudge(step),
        escape: () => h.select(null),
        delete: h.actions.remove,
        backspace: h.actions.remove,
        "+": () => h.zoom(2),
        "=": () => h.zoom(2),
        "-": () => h.zoom(0.5),
      };
      const key = event.key.toLowerCase();
      const handler = event.metaKey || event.ctrlKey ? commands[key] : plain[key];
      if (!handler) return;
      event.preventDefault();
      handler();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!edit || !rendered) return null;

  const shown = editing ? rendered : { buffer: original, blocks: originalBlocks };
  const gainDb = edit.gain_db;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-3 border-b border-border px-6 py-3">
        {dirty ? (
          <ConfirmButton variant="ghost" size="sm" confirmLabel="Leave without saving?" onConfirm={() => router.back()}>
            <ArrowLeft /> Library
          </ConfirmButton>
        ) : (
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft /> Library
          </Button>
        )}
        <div className="min-w-0 flex-1 truncate text-sm">
          <span className="text-muted-foreground">{track.artist ?? "Unknown artist"} – </span>
          <span className="font-medium">{trackTitle(track)}</span>
          {dirty && <span className="ml-2 text-xs text-primary">● unsaved</span>}
        </div>
        <Button variant="ghost" size="icon-sm" title="Undo (⌘Z)" disabled={!past.length} onClick={undo}>
          <Undo2 />
        </Button>
        <Button variant="ghost" size="icon-sm" title="Redo (⌘⇧Z)" disabled={!future.length} onClick={redo}>
          <Redo2 />
        </Button>
        <ConfirmButton
          variant="ghost"
          size="sm"
          disabled={isIdentity(edit, original.length) && !savedJson}
          confirmLabel="Reset this edit? All changes will be lost"
          onConfirm={() => void reset()}
        >
          Reset to original
        </ConfirmButton>
        <Button variant="outline" size="sm" disabled={busy !== null || !dirty} onClick={() => void save()} title="Save edit (⌘S)">
          <Save /> {busy === "save" ? "Saving…" : "Save edit"}
        </Button>
        <div className="relative">
          <Button size="sm" disabled={busy !== null} onClick={() => setExportOpen((open) => !open)}>
            <Download /> {busy === "export" ? "Exporting…" : "Export"}
          </Button>
          {exportOpen && (
            <div className="absolute top-full right-0 z-20 mt-2 flex w-72 flex-col gap-3 rounded-lg border border-border bg-popover p-4 text-sm shadow-lg">
              <p className="text-xs text-muted-foreground">
                Writes a new file “{track.filename.replace(/\.[^.]+$/, "")} (Edited)” in the edits folder. The original is
                never modified.
              </p>
              <div className="flex gap-2">
                {(["wav", "mp3"] as const).map((value) => (
                  <Button
                    key={value}
                    size="sm"
                    variant={format === value ? "secondary" : "outline"}
                    className="flex-1 uppercase"
                    onClick={() => {
                      setFormat(value);
                      setQuality(QUALITIES[value][0]);
                    }}
                  >
                    {value}
                  </Button>
                ))}
              </div>
              <label className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">{format === "wav" ? "Bit depth" : "Bitrate"}</span>
                <select
                  className="rounded-md border border-border bg-background px-2 py-1"
                  value={quality}
                  onChange={(event) => setQuality(Number(event.target.value) as EditExportRequest["quality"])}
                >
                  {QUALITIES[format].map((value) => (
                    <option key={value} value={value}>
                      {format === "wav" ? `${value}-bit` : `${value} kbps`}
                    </option>
                  ))}
                </select>
              </label>
              <Button disabled={busy !== null} onClick={() => void exportFile()}>
                {busy === "export" ? "Exporting…" : "Export as new file"}
              </Button>
            </div>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-6 py-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-sm tabular-nums">
          <span>{formatBpm(track.bpm)} BPM</span>
          <KeyBadge camelot={track.camelot_key} />
          <span className="text-muted-foreground">
            {clock(original.duration)}
            {editLength(edit) !== original.length && <span className="text-foreground"> → {clock(editLength(edit) / rate)}</span>}
          </span>
          {editing && selection && (
            <span className="text-primary">
              Selection {clock(selection.start / rate)} – {clock(selection.end / rate)} ({clock((selection.end - selection.start) / rate)})
            </span>
          )}
          {!editing && <span className="font-sans text-xs text-muted-foreground">Listening to the original — switch to B to edit</span>}
        </div>

        <section className={cn("rounded-lg border bg-card p-3", editing ? "border-border" : "border-primary/50")}>
          <EditorWaveform
            ref={waveform}
            buffer={shown.buffer}
            blocks={shown.blocks}
            gain={editing ? 10 ** (gainDb / 20) : 1}
            editable={editing}
            selection={selection}
            boundaries={editing ? segmentJoins(edit) : []}
            getPosition={getPosition}
            playing={state.playing}
            onSeek={(frame) => engine.seek(frame / rate)}
            onSelect={select}
          />
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <Tool label="Cut" shortcut="⌘X" disabled={!editing} onClick={actions.cut}>
              <Scissors />
            </Tool>
            <Tool label="Copy" shortcut="⌘C" disabled={!editing} onClick={actions.copy}>
              <Copy />
            </Tool>
            <Tool label="Paste" shortcut="⌘V" disabled={!editing || !clipboard} onClick={actions.paste}>
              <ClipboardPaste />
            </Tool>
            <Tool label="Duplicate" shortcut="⌘D" disabled={!editing} onClick={actions.duplicate}>
              <CopyPlus />
            </Tool>
            <Tool label="Split" shortcut="at the playhead" disabled={!editing} onClick={actions.split}>
              <SquareSplitHorizontal />
            </Tool>
            <Tool label="Trim" shortcut="keep the selection" disabled={!editing} onClick={actions.trim} />
            <Tool label="Delete" shortcut="⌫" disabled={!editing} onClick={actions.remove}>
              <Trash2 />
            </Tool>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Tool label="Fade in" disabled={!editing} onClick={() => actions.fade("in")} />
            <Tool label="Fade out" disabled={!editing} onClick={() => actions.fade("out")} />
            <Tool label="Normalize" shortcut="peak to −1 dBFS" disabled={!editing} onClick={actions.normalize} />
            <div className="ml-4 flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Gain</span>
              <span className="font-mono text-xs text-muted-foreground">−{GAIN_SLIDER_DB}</span>
              <input
                type="range"
                min={-GAIN_SLIDER_DB}
                max={GAIN_SLIDER_DB}
                step={0.1}
                value={Math.max(-GAIN_SLIDER_DB, Math.min(GAIN_SLIDER_DB, gainDb))}
                disabled={!editing}
                onChange={(event) => actions.gain(Number(event.target.value))}
                onDoubleClick={() => actions.gain(0)}
                className="w-48 accent-primary"
                aria-label="Gain"
              />
              <span className="font-mono text-xs text-muted-foreground">+{GAIN_SLIDER_DB}</span>
              <span className={cn("w-16 text-right font-mono text-xs tabular-nums", gainDb !== 0 && "text-primary")}>
                {gainDb > 0 ? "+" : ""}
                {gainDb.toFixed(1)} dB
              </span>
              <Button variant="ghost" size="xs" disabled={!editing || gainDb === 0} onClick={() => actions.gain(0)}>
                0 dB
              </Button>
              {editing && rendered.peak * 10 ** (gainDb / 20) > 1 && <span className="text-xs text-destructive">clipping</span>}
            </div>
          </div>
        </section>

        <section className="flex items-center justify-center gap-2 border-t border-border pt-4">
          <Button variant="ghost" size="icon-sm" title="Start (Home)" onClick={transport.home}>
            <SkipBack />
          </Button>
          <Button size="icon-lg" className="rounded-full" title="Play / Pause (Space)" onClick={transport.toggle}>
            {state.playing ? <Pause /> : <Play />}
          </Button>
          <Button variant="ghost" size="icon-sm" title="Stop" onClick={transport.stop}>
            <Square />
          </Button>
          <Clock engine={engine} />
          <Button variant="outline" size="sm" disabled={!editing || !selection} onClick={transport.playSelection}>
            <Play /> Selection
          </Button>
          <Button variant={state.loop ? "secondary" : "ghost"} size="sm" title="Loop the selection" onClick={transport.loop}>
            <Repeat /> Loop
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-24 font-mono"
            title="Compare the original (A) and the edit (B) at the same moment"
            onClick={transport.ab}
          >
            <span className={cn(!editing && "text-primary")}>A</span>/<span className={cn(editing && "text-primary")}>B</span>
          </Button>
          <div className="ml-4 flex items-center gap-1">
            <Button variant="ghost" size="icon-sm" title="Zoom out (−)" onClick={() => waveform.current?.zoom(0.5, playhead())}>
              <Minus />
            </Button>
            <Button variant="ghost" size="icon-sm" title="Zoom in (+)" onClick={() => waveform.current?.zoom(2, playhead())}>
              <Plus />
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
