"use client";

import type { ShortFolder, TrashResult } from "@cueflow/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { MiniPlay } from "@/components/cleanup/MiniPlay";
import { TrashNotice } from "@/components/cleanup/TrashNotice";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { api } from "@/lib/api";
import { formatBytes, formatDuration, trackTitle } from "@/lib/format";
import { cn } from "@/lib/utils";

const THRESHOLDS = [15, 30, 60, 90, 120];

function FolderRow({ folder, maxMs, checked, onToggle }: { folder: ShortFolder; maxMs: number; checked: boolean; onToggle: () => void }) {
  const [open, setOpen] = useState(false);
  const tracks = useQuery({ queryKey: ["short", "tracks", folder.folder, maxMs], queryFn: () => api.shortTracksIn(folder.folder, maxMs), enabled: open });

  return (
    <li className="border-b border-border/40">
      <div className="flex items-center gap-3 px-4 py-2 text-sm">
        <input type="checkbox" checked={checked} onChange={onToggle} aria-label={`Select ${folder.folder}`} className="accent-[var(--primary)]" />
        <button type="button" onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
          <ChevronRight className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")} />
          <span className="truncate font-mono text-xs">{folder.folder === "." ? "(Music root)" : folder.folder.replaceAll(":", "/")}</span>
          {folder.sample_folder && (
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground" title="Looks like a DJ tools / samples folder">
              samples
            </span>
          )}
        </button>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">{folder.count} files</span>
        <span className="w-16 text-right font-mono text-xs text-muted-foreground tabular-nums">{formatBytes(folder.bytes)}</span>
      </div>
      {open && (
        <ul className="pb-2 pl-14">
          {tracks.data?.slice(0, 200).map((track) => (
            <li key={track.id} className="flex items-center gap-2 py-0.5 text-xs text-muted-foreground">
              <MiniPlay track={track} />
              <span className="min-w-0 flex-1 truncate">{trackTitle(track)}</span>
              <span className="font-mono tabular-nums">{formatDuration(track.duration_ms)}</span>
            </li>
          ))}
          {tracks.data && tracks.data.length > 200 && <li className="py-1 text-[11px] text-muted-foreground">… and {tracks.data.length - 200} more</li>}
        </ul>
      )}
    </li>
  );
}

export function ShortTracks() {
  const client = useQueryClient();
  const [seconds, setSeconds] = useState(60);
  const maxMs = seconds * 1000;
  const [result, setResult] = useState<TrashResult>();
  // Explicit choices override the default (every folder except sample packs).
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const { data, error, isLoading } = useQuery({ queryKey: ["short", maxMs], queryFn: () => api.shortTracks(maxMs) });

  const isChecked = (f: ShortFolder) => overrides[f.folder] ?? !f.sample_folder;
  const selected = data?.folders.filter(isChecked) ?? [];
  const selectedCount = selected.reduce((sum, f) => sum + f.count, 0);
  const selectedBytes = selected.reduce((sum, f) => sum + f.bytes, 0);

  const remove = useMutation({
    mutationFn: () => api.deleteShort(maxMs, selected.map((f) => f.folder)),
    onSuccess: (r) => {
      setResult(r);
      setOverrides({});
      for (const key of ["short", "tracks", "folders", "facets", "duplicates"]) void client.invalidateQueries({ queryKey: [key] });
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <span className="text-sm">Shorter than</span>
        {THRESHOLDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setSeconds(s);
              setOverrides({});
            }}
            className={cn("rounded-md border px-2 py-0.5 font-mono text-xs", seconds === s ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:bg-muted")}
          >
            {s}s
          </button>
        ))}
        <span className="text-xs text-muted-foreground">{data?.total ?? 0} files in {data?.folders.length ?? 0} folders</span>
        <ConfirmButton
          size="sm"
          className="ml-auto"
          disabled={!selectedCount || remove.isPending}
          onConfirm={() => remove.mutate()}
          confirmLabel={`Confirm: move ${selectedCount} files to the Trash`}
        >
          Trash {selectedCount} selected ({formatBytes(selectedBytes)})
        </ConfirmButton>
      </div>
      <TrashNotice result={result} />
      <ErrorNotice error={error} action="Loading short tracks" />
      <ErrorNotice error={remove.error} action="Moving files to the Trash" />
      <p className="border-b border-border px-4 py-2 text-[11px] text-muted-foreground">
        Folders that look like DJ tools or sample packs (TOOLS, VOCALS, VOX…) are not selected by default. Expand a folder to listen before deleting.
      </p>
      <ul className="min-h-0 flex-1 overflow-auto">
        {data?.folders.map((folder) => (
          <FolderRow
            key={folder.folder}
            folder={folder}
            maxMs={maxMs}
            checked={isChecked(folder)}
            onToggle={() => setOverrides({ ...overrides, [folder.folder]: !isChecked(folder) })}
          />
        ))}
        {isLoading && <p className="px-4 py-16 text-center text-sm text-muted-foreground">Loading…</p>}
        {data?.total === 0 && <p className="px-4 py-16 text-center text-sm text-muted-foreground">No track shorter than {seconds}s.</p>}
      </ul>
    </div>
  );
}
