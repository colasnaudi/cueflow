"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AudioWaveform, Square } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function AnalysisControl() {
  const client = useQueryClient();
  const { data: status, refetch } = useQuery({
    queryKey: ["analysis"],
    queryFn: api.analysisStatus,
    refetchInterval: (query) => (query.state.data?.running ? 2000 : false),
  });
  const lastProcessed = useRef(0);

  // New suggestions land while the job runs: refresh the queue every 10 analysed tracks, and at the end.
  useEffect(() => {
    if (!status) return;
    const done = !status.running && lastProcessed.current > 0;
    if (status.processed - lastProcessed.current >= 10 || done) {
      void client.invalidateQueries({ queryKey: ["reviews"] });
    }
    lastProcessed.current = status.running ? status.processed : 0;
  }, [status, client]);

  const running = !!status?.running;
  const progress = status?.total ? Math.round((status.processed / status.total) * 100) : 0;

  return (
    <div className="flex items-center gap-3">
      {running && (
        <div className="flex w-72 flex-col gap-1">
          <div className="flex justify-between font-mono text-[11px] text-muted-foreground tabular-nums">
            <span>{status?.phase === "folders" ? "Reading folders…" : `Analysing ${status?.processed}/${status?.total}`}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1 overflow-hidden rounded bg-muted">
            <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
          </div>
          {status?.current && <span className="truncate text-[11px] text-muted-foreground">{status.current}</span>}
        </div>
      )}
      {!running && status?.state === "failed" && (
        <span className="max-w-72 truncate text-[11px] text-destructive" title={status.error ?? undefined}>
          Analysis failed: {status.error}
        </span>
      )}
      {!running && (status?.state === "completed" || status?.state === "stopped") && (
        <span className="text-[11px] text-muted-foreground">
          {status.state === "stopped" ? "Stopped" : "Last run"}: {status.analyzed} analysed
          {status.error_count > 0 && ` · ${status.error_count} errors`}
        </span>
      )}
      {running ? (
        <Button variant="outline" size="sm" onClick={() => api.stopAnalysis().then(() => refetch())}>
          <Square /> Stop
        </Button>
      ) : (
        <Button size="sm" onClick={() => api.startAnalysis().catch(() => undefined).finally(() => refetch())} title="Suggest genres from your folders, then from the audio (≈1.5 s per track)">
          <AudioWaveform /> Analyse library
        </Button>
      )}
    </div>
  );
}
