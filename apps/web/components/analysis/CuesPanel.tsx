"use client";

import type { Cue, Track, TrackAnalysis } from "@cueflow/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Play, RotateCcw, X } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { api } from "@/lib/api";
import { barStarts, positionLabel, positionTime } from "@/lib/beatgrid";
import { cn } from "@/lib/utils";
import { usePlayer } from "@/lib/player";

function formatCueTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

/** Suggested hot cues and memory cues: listen, remove, approve — approved cues are what gets exported. */
export function CuesPanel({ track, analysis }: { track: Track; analysis: TrackAnalysis | undefined }) {
  const client = useQueryClient();
  const { data: cues } = useQuery({ queryKey: ["cues", track.id], queryFn: () => api.cues(track.id) });
  const setCues = (value: Cue[]) => client.setQueryData(["cues", track.id], value);
  const approve = useMutation({ mutationFn: () => api.approveCues(track.id), onSuccess: setCues });
  const regenerate = useMutation({ mutationFn: () => api.regenerateCues(track.id), onSuccess: setCues });
  const remove = useMutation({ mutationFn: (cueId: string) => api.deleteCue(track.id, cueId), onSuccess: setCues });

  const grid = analysis?.beatgrid;
  if (!grid || !cues) return null;
  const duration = (track.duration_ms ?? 0) / 1000;
  const starts = barStarts(grid, duration);
  const hot = cues.filter((c) => c.type === "HOT");
  const memory = cues.filter((c) => c.type === "MEMORY");
  const pending = cues.some((c) => !c.approved);

  return (
    <section className="rounded-lg border border-border px-4 py-2">
      <header className="flex items-center gap-2 border-b border-border/60 py-2">
        <h2 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Cues</h2>
        <span className={cn("rounded px-1.5 py-0.5 text-[10px]", pending ? "bg-amber-500/15 text-amber-300" : "bg-primary/15 text-primary")}>
          {pending ? "suggested — not approved" : "approved · ready for Rekordbox"}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="xs" onClick={() => regenerate.mutate()} disabled={regenerate.isPending} title="Re-plan the suggestions from the sections (approved cues are kept)">
            <RotateCcw /> Regenerate
          </Button>
          {pending && (
            <Button size="xs" onClick={() => approve.mutate()} disabled={approve.isPending}>
              <Check /> Approve cues
            </Button>
          )}
          <Button variant="outline" size="xs" nativeButton={false} render={<Link href="/export" />}>
            Rekordbox export
          </Button>
        </div>
      </header>
      <ErrorNotice error={approve.error ?? regenerate.error ?? remove.error} action="Cues" className="mt-2 rounded border" />

      <ul className="divide-y divide-border/40">
        {hot.map((cue) => {
          const at = positionTime(grid, starts, cue.bar, cue.beat, duration);
          return (
            <li key={cue.id} className="flex items-center gap-3 py-1.5 text-sm">
              <span className="flex size-6 items-center justify-center rounded font-mono text-xs font-bold text-black" style={{ backgroundColor: cue.color ?? "#888" }}>
                {cue.slot}
              </span>
              <span className="w-20 font-medium">{cue.label}</span>
              <span className="font-mono text-xs tabular-nums">{formatCueTime(at)}</span>
              <span className="font-mono text-[11px] text-muted-foreground">bar {positionLabel(cue.bar, cue.beat)}</span>
              {cue.approved ? <Check className="size-3.5 text-primary" aria-label="approved" /> : <span className="text-[10px] text-amber-300">suggested</span>}
              <div className="ml-auto flex items-center">
                <Button variant="ghost" size="icon-xs" aria-label={`Play from cue ${cue.slot}`} onClick={() => usePlayer.getState().play(track, at)}>
                  <Play />
                </Button>
                <Button variant="ghost" size="icon-xs" aria-label={`Remove cue ${cue.slot}`} onClick={() => remove.mutate(cue.id)} disabled={remove.isPending}>
                  <X />
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      {memory.length > 0 && (
        <p className="py-2 text-[11px] text-muted-foreground">
          + {memory.length} memory cues on the section starts ({memory.map((c) => c.label).join(" · ")}) — structure markers in Rekordbox.
        </p>
      )}
    </section>
  );
}
