"use client";

import type { AnalysisStatus } from "@cueflow/types";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Square } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface JobControlProps {
  id: string;
  status: () => Promise<AnalysisStatus>;
  start: () => Promise<unknown>;
  stop: () => Promise<unknown>;
  /** Queries refreshed every 10 processed items and when the job ends. */
  invalidate: string[][];
  label: string;
  icon: React.ReactNode;
  hint?: string;
  compact?: boolean;
}

/** Start / stop / progress of a background job. */
export function JobControl({ id, status: fetchStatus, start, stop, invalidate, label, icon, hint, compact }: JobControlProps) {
  const client = useQueryClient();
  const { data: status, refetch } = useQuery({
    queryKey: ["job", id],
    queryFn: fetchStatus,
    refetchInterval: (query) => (query.state.data?.running ? 2000 : false),
  });
  const lastProcessed = useRef(0);

  useEffect(() => {
    if (!status) return;
    const done = !status.running && lastProcessed.current > 0;
    if (status.processed - lastProcessed.current >= 10 || done) {
      for (const key of invalidate) void client.invalidateQueries({ queryKey: key });
      lastProcessed.current = status.processed;
    }
    if (!status.running) lastProcessed.current = 0;
  }, [status, client, invalidate]);

  const running = !!status?.running;
  const progress = status?.total ? Math.round((status.processed / status.total) * 100) : 0;

  return (
    <div className={cn("flex gap-3", compact ? "flex-col gap-1.5" : "items-center")}>
      {running && (
        <div className={cn("flex flex-col gap-1", !compact && "w-72")}>
          <div className="flex justify-between font-mono text-[11px] text-muted-foreground tabular-nums">
            <span className="truncate">
              {status?.scope && <span title={status.scope}>{status.scope.split("/").pop()?.replaceAll(":", "/")} · </span>}
              {status?.phase === "folders" ? "Reading folders…" : status?.phase === "cues" ? "Cues…" : `${status?.processed}/${status?.total}`}
            </span>
            <span>{progress}%</span>
          </div>
          <div className="h-1 overflow-hidden rounded bg-muted">
            <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
          </div>
          {status?.current && <span className="truncate text-[11px] text-muted-foreground">{status.current}</span>}
        </div>
      )}
      {!running && status?.state === "failed" && (
        <span className="truncate text-[11px] text-destructive" title={status.error ?? undefined}>
          Failed: {status.error}
        </span>
      )}
      {!running && (status?.state === "completed" || status?.state === "stopped") && (
        <span className="text-[11px] text-muted-foreground">
          {status.state === "stopped" ? "Stopped" : "Done"}: {status.analyzed} analysed
          {status.error_count > 0 && ` · ${status.error_count} errors`}
        </span>
      )}
      {running ? (
        <Button variant="outline" size="sm" onClick={() => stop().then(() => refetch())}>
          <Square /> Stop
        </Button>
      ) : (
        <Button size="sm" variant={compact ? "outline" : "default"} onClick={() => start().catch(() => undefined).finally(() => refetch())} title={hint}>
          {icon} {label}
        </Button>
      )}
    </div>
  );
}
