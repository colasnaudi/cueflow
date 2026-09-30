"use client";

import type { DuplicateGroup, DuplicateKind, TrashResult } from "@cueflow/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { MiniPlay } from "@/components/cleanup/MiniPlay";
import { TrashNotice } from "@/components/cleanup/TrashNotice";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { api } from "@/lib/api";
import { formatBytes, formatDuration, trackTitle } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 30;

function Group({ group, kind, onResolved }: { group: DuplicateGroup; kind: DuplicateKind; onResolved: (r: TrashResult) => void }) {
  const [kept, setKept] = useState(() => new Set(group.keep_ids));
  const removable = group.copies.filter((c) => !kept.has(c.track.id) && !c.protected);
  const resolve = useMutation({
    // Ratings and tags of removed copies are merged into the first kept copy.
    mutationFn: () => api.resolveDuplicates([...kept][0], removable.map((c) => c.track.id)),
    onSuccess: onResolved,
  });
  const failed = resolve.error;
  const toggle = (id: string) => {
    const next = new Set(kept);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    if (next.size > 0) setKept(next); // at least one copy always stays
  };
  const first = group.copies[0].track;

  return (
    <section className="border-b border-border/60 px-4 py-3">
      <header className="mb-2 flex items-center gap-3">
        <div className="min-w-0">
          <span className="text-sm font-medium">{trackTitle(first)}</span>
          <span className="text-sm text-muted-foreground"> · {first.artist ?? "Unknown artist"}</span>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{group.copies.length} copies</span>
        <ConfirmButton
          size="xs"
          variant="outline"
          className="ml-auto"
          disabled={resolve.isPending || removable.length === 0}
          onConfirm={() => resolve.mutate()}
          confirmLabel={`Confirm: trash ${removable.length}`}
        >
          {removable.length ? `Trash ${removable.length} unchecked cop${removable.length > 1 ? "ies" : "y"}` : "Nothing to remove"}
        </ConfirmButton>
      </header>
      <ErrorNotice error={failed} action="Removing duplicates" className="mb-2 rounded border" />
      <ul className="flex flex-col">
        {group.copies.map(({ track, folder, protected: isProtected }) => {
          const keep = kept.has(track.id) || isProtected;
          return (
            <li key={track.id} className={cn("flex items-center gap-3 rounded px-2 py-1 text-xs", keep ? "bg-primary/10" : "text-muted-foreground line-through decoration-muted-foreground/40")}>
              <input
                type="checkbox"
                checked={keep}
                disabled={isProtected}
                onChange={() => toggle(track.id)}
                aria-label={`Keep the copy in ${folder}`}
                className="accent-[var(--primary)]"
              />
              <MiniPlay track={track} />
              <span className="min-w-0 flex-1 truncate font-mono" title={track.path}>
                {folder === "." ? "(Music root)" : folder.replaceAll(":", "/")}/{track.filename}
              </span>
              {kind === "probable" && <span className="font-mono tabular-nums">{formatDuration(track.duration_ms)}</span>}
              <span className="w-24 text-right font-mono tabular-nums">
                {track.filename.split(".").pop()?.toUpperCase()} {track.bitrate ? `${track.bitrate}k` : ""}
              </span>
              <span className="w-14 text-right font-mono tabular-nums">{formatBytes(track.file_size)}</span>
              <span className="w-10 text-amber-400">{"★".repeat(track.rating)}</span>
              <span className={cn("w-20 text-right text-[10px] font-medium uppercase", keep ? "text-primary" : "text-destructive")}>
                {isProtected ? "Apple Music" : keep ? "keep" : "trash"}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function Duplicates() {
  const client = useQueryClient();
  const [kind, setKind] = useState<DuplicateKind>("exact");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [result, setResult] = useState<TrashResult>();
  const { data, isLoading, error } = useQuery({ queryKey: ["duplicates", kind, limit], queryFn: () => api.duplicates(kind, 0, limit) });

  const onResolved = (r: TrashResult) => {
    setResult(r);
    for (const key of ["duplicates", "tracks", "folders", "facets", "short"]) void client.invalidateQueries({ queryKey: [key] });
  };
  const resolveAll = useMutation({ mutationFn: api.resolveAllExact, onSuccess: onResolved });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        {(["exact", "probable"] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => {
              setKind(k);
              setLimit(PAGE_SIZE);
            }}
            className={cn("rounded-md px-2.5 py-1 text-sm text-muted-foreground hover:bg-muted", kind === k && "bg-muted text-foreground")}
          >
            {k === "exact" ? "Identical files" : "Probable (same artist, title, length)"}
          </button>
        ))}
        {data && (
          <span className="text-xs text-muted-foreground">
            {data.total_groups} groups · {data.removable_files} removable files · {formatBytes(data.removable_bytes)}
          </span>
        )}
        {kind === "exact" && !!data?.total_groups && (
          <ConfirmButton
            size="sm"
            className="ml-auto"
            disabled={resolveAll.isPending}
            onConfirm={() => resolveAll.mutate()}
            confirmLabel={`Confirm: move ${data.removable_files} files to the Trash`}
          >
            Resolve all ({formatBytes(data.removable_bytes)})
          </ConfirmButton>
        )}
      </div>
      <TrashNotice result={result} />
      <ErrorNotice error={error} action="Loading duplicates" />
      <ErrorNotice error={resolveAll.error} action="Resolving all duplicates" />
      <p className="border-b border-border px-4 py-2 text-[11px] text-muted-foreground">
        {kind === "exact"
          ? "Byte-identical files. Kept by default: every copy in your numbered folders (a track can live in TECH_HOUSE and UK_HOUSE on purpose) — only stray copies are trashed. Apple Music files are never touched. Ratings and tags are merged into the kept copy."
          : "Different files that look like the same track (other encode or other tags). Listen before choosing — they may be different edits."}
      </p>
      <div className="min-h-0 flex-1 overflow-auto">
        {data?.groups.map((group) => <Group key={`${kind}-${group.copies[0].track.id}`} group={group} kind={kind} onResolved={onResolved} />)}
        {isLoading && <p className="px-4 py-16 text-center text-sm text-muted-foreground">Looking for duplicates…</p>}
        {!isLoading && data?.total_groups === 0 && <p className="px-4 py-16 text-center text-sm text-muted-foreground">No duplicates. 🎉</p>}
        {data && data.groups.length < data.total_groups && (
          <div className="p-4 text-center">
            <Button variant="outline" size="sm" onClick={() => setLimit(limit + PAGE_SIZE)}>
              Show more ({data.total_groups - data.groups.length} left)
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
