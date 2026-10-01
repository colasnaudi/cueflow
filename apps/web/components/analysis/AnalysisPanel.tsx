"use client";

import type { Track, TrackAnalysis } from "@cueflow/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AudioLines, ChevronLeft, ChevronRight, Loader2, Play, RotateCcw, TriangleAlert } from "lucide-react";

import { KeyBadge } from "@/components/library/KeyBadge";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { api } from "@/lib/api";
import { SECTION_STYLE, TRUSTED_DOWNBEAT, TRUSTED_GRID, barStarts, barTime, firstDownbeat } from "@/lib/beatgrid";
import { formatBpm, formatTime } from "@/lib/format";
import { applyTrackUpdate } from "@/lib/mutations";
import { usePlayer } from "@/lib/player";
import { cn } from "@/lib/utils";

const SOURCE_LABEL = { TAG: "file tag", ANALYSIS: "analysis", USER: "you" } as const;

function Row({ label, children, warning }: { label: string; children: React.ReactNode; warning?: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[6rem_minmax(0,1fr)] items-start gap-3 py-2 text-sm">
      <dt className="pt-0.5 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">{label}</dt>
      <dd className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">{children}</div>
        {warning && (
          <p className="flex items-center gap-1 text-[11px] text-amber-400">
            <TriangleAlert className="size-3" /> {warning}
          </p>
        )}
      </dd>
    </div>
  );
}

function Percent({ value }: { value: number | null }) {
  if (value == null) return null;
  return <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{Math.round(value * 100)}% sure</span>;
}

export function AnalysisPanel({ track, analysis }: { track: Track; analysis: TrackAnalysis | undefined }) {
  const client = useQueryClient();
  const setAnalysis = (value: TrackAnalysis) => {
    client.setQueryData(["analysis", track.id], value);
    void client.invalidateQueries({ queryKey: ["track", track.id] });
    void client.invalidateQueries({ queryKey: ["tracks"] });
  };
  const analyse = useMutation({ mutationFn: (reset: boolean) => api.analyseTrack(track.id, reset), onSuccess: setAnalysis });
  const shift = useMutation({ mutationFn: (beats: number) => api.shiftDownbeat(track.id, beats), onSuccess: setAnalysis });
  const apply = useMutation({
    mutationFn: (fields: ("bpm" | "key")[]) => api.applyAnalysis(track.id, fields),
    onSuccess: (updated) => applyTrackUpdate(client, updated),
  });

  const grid = analysis?.beatgrid;
  const busy = analyse.isPending;

  if (!grid) {
    return (
      <section className="flex items-center gap-3 rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
        <AudioLines className="size-4" />
        <span className="flex-1">Not analysed yet: BPM, beatgrid, bar 1, key and energy come from the audio.</span>
        <Button size="sm" onClick={() => analyse.mutate(false)} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <AudioLines />} {busy ? "Analysing… (~5 s)" : "Analyse now"}
        </Button>
        <ErrorNotice error={analyse.error} action="Analysis" className="rounded border" />
      </section>
    );
  }

  const bpmDiffers = track.bpm != null && Math.abs(track.bpm - grid.bpm) >= 0.05;
  const keyDiffers = !!analysis?.camelot_key && track.camelot_key !== analysis.camelot_key;
  const downbeat = firstDownbeat(grid);
  const duration = (track.duration_ms ?? 0) / 1000;
  const starts = barStarts(grid, duration);

  return (
    <section className="rounded-lg border border-border px-4 py-2">
      <header className="flex items-center gap-2 border-b border-border/60 py-2">
        <h2 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Audio analysis</h2>
        <Button variant="ghost" size="xs" className="ml-auto" onClick={() => analyse.mutate(false)} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <RotateCcw />} Re-analyse
        </Button>
      </header>
      <ErrorNotice error={analyse.error ?? shift.error ?? apply.error} action="Analysis" className="mt-2 rounded border" />

      <dl className="divide-y divide-border/40">
        <Row label="BPM" warning={(grid.grid_confidence ?? 0) < TRUSTED_GRID ? "Irregular beats: the tempo may vary — check the grid by ear." : undefined}>
          <span className="font-mono text-base tabular-nums">{formatBpm(grid.bpm)}</span>
          <Percent value={grid.grid_confidence} />
          {track.bpm != null && (
            <span className={cn("text-xs", bpmDiffers ? "text-amber-400" : "text-muted-foreground")}>
              catalogue {formatBpm(track.bpm)} ({SOURCE_LABEL[track.bpm_source ?? "TAG"]})
            </span>
          )}
          {bpmDiffers && (
            <Button size="xs" variant="outline" onClick={() => apply.mutate(["bpm"])} disabled={apply.isPending}>
              Use {formatBpm(grid.bpm)}
            </Button>
          )}
        </Row>

        <Row label="Key">
          {analysis?.camelot_key ? (
            <>
              <KeyBadge camelot={analysis.camelot_key} />
              <span className="text-xs text-muted-foreground">{analysis.musical_key}</span>
              <Percent value={analysis.key_strength} />
            </>
          ) : (
            <span className="text-xs text-muted-foreground">not detected</span>
          )}
          {track.camelot_key && (
            <span className={cn("text-xs", keyDiffers ? "text-amber-400" : "text-muted-foreground")}>
              catalogue {track.camelot_key} ({SOURCE_LABEL[track.key_source ?? "TAG"]})
            </span>
          )}
          {keyDiffers && (
            <Button size="xs" variant="outline" onClick={() => apply.mutate(["key"])} disabled={apply.isPending}>
              Use {analysis?.camelot_key}
            </Button>
          )}
        </Row>

        <Row
          label="Bar 1"
          warning={
            grid.source !== "USER" && (grid.downbeat_confidence ?? 0) < TRUSTED_DOWNBEAT
              ? "Unsure where bars start: listen and move bar 1 if the numbers are off."
              : undefined
          }
        >
          <span className="font-mono text-sm tabular-nums">{formatTime(downbeat)}</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">.{String(Math.round((downbeat % 1) * 1000)).padStart(3, "0")}</span>
          {grid.source === "USER" ? (
            <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">adjusted by you</span>
          ) : (
            <Percent value={grid.downbeat_confidence} />
          )}
          <Button size="xs" variant="ghost" onClick={() => usePlayer.getState().play(track, Math.max(0, downbeat))} title="Play from bar 1">
            <Play /> Listen
          </Button>
          <div className="flex items-center">
            <Button size="icon-xs" variant="outline" aria-label="Move bar 1 one beat earlier" onClick={() => shift.mutate(-1)} disabled={shift.isPending}>
              <ChevronLeft />
            </Button>
            <span className="px-1.5 text-[11px] text-muted-foreground">1 beat</span>
            <Button size="icon-xs" variant="outline" aria-label="Move bar 1 one beat later" onClick={() => shift.mutate(1)} disabled={shift.isPending}>
              <ChevronRight />
            </Button>
          </div>
          {grid.source === "USER" && (
            <Button size="xs" variant="ghost" onClick={() => analyse.mutate(true)} disabled={busy} title="Discard your correction and use the analysis again">
              Reset
            </Button>
          )}
        </Row>
        <Row label="Structure">
          {analysis?.sections.length ? (
            analysis.sections.map((section) => {
              const style = SECTION_STYLE[section.type];
              return (
                <button
                  key={`${section.type}${section.start_bar}`}
                  type="button"
                  onClick={() => usePlayer.getState().play(track, barTime(starts, section.start_bar, duration))}
                  className={cn("rounded px-1.5 py-0.5 text-[11px] hover:ring-1 hover:ring-foreground/40", style.className)}
                  title={`Play from bar ${section.start_bar + 1} (${formatTime(barTime(starts, section.start_bar, duration))})`}
                >
                  {style.label} <span className="font-mono opacity-70">{section.start_bar + 1}</span>
                </button>
              );
            })
          ) : (
            <span className="text-xs text-muted-foreground">no clear sections (too short or no kick pattern)</span>
          )}
        </Row>

        <Row label="Vocals">
          {analysis?.vocal_probability != null ? (
            <span className="text-xs">
              voice on <span className="font-mono tabular-nums">{Math.round(analysis.vocal_probability * 100)}%</span> of the track
              <span className="text-muted-foreground"> · cyan strip on the waveform</span>
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">re-analyse to detect vocals</span>
          )}
        </Row>
      </dl>
    </section>
  );
}
