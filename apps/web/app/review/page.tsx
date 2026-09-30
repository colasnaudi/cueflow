"use client";

import type { ReviewStatus } from "@cueflow/types";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AudioWaveform } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { JobControl } from "@/components/JobControl";
import { ReviewRow } from "@/components/review/ReviewRow";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { api } from "@/lib/api";
import { applyTrackUpdate } from "@/lib/mutations";
import { usePlayer } from "@/lib/player";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;
const GENRE_JOB_REFRESH = [["reviews"]];
const TABS: { status: ReviewStatus; label: string }[] = [
  { status: "PENDING", label: "To review" },
  { status: "APPROVED", label: "Approved" },
  { status: "REJECTED", label: "Rejected" },
];

function isTyping(target: EventTarget | null) {
  return target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
}

export default function ReviewPage() {
  const client = useQueryClient();
  const [status, setStatus] = useState<ReviewStatus>("PENDING");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(0);

  const reviews = useQuery({
    queryKey: ["reviews", status, page],
    queryFn: () => api.reviews(status, page * PAGE_SIZE, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const facets = useQuery({ queryKey: ["facets", undefined], queryFn: () => api.facets() });
  const items = useMemo(() => reviews.data?.items ?? [], [reviews.data]);
  const counts = reviews.data?.counts;
  const pages = Math.max(1, Math.ceil((reviews.data?.total ?? 0) / PAGE_SIZE));

  const act = useMutation({
    mutationFn: ({ trackId, action, genre }: { trackId: string; action: "approve" | "reject" | "reset"; genre?: string }) =>
      api.reviewGenre(trackId, action, genre),
    onSuccess: (item) => {
      applyTrackUpdate(client, item.track);
      void client.invalidateQueries({ queryKey: ["reviews"] });
      void client.invalidateQueries({ queryKey: ["facets"] });
    },
  });
  const bulk = useMutation({
    mutationFn: (ids: string[]) => api.bulkApprove(ids),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["reviews"] });
      void client.invalidateQueries({ queryKey: ["tracks"] });
      void client.invalidateQueries({ queryKey: ["facets"] });
    },
  });

  const approve = useCallback((index: number, genre: string) => {
    const item = items[index];
    if (item) act.mutate({ trackId: item.track.id, action: "approve", genre });
  }, [items, act]);
  const reject = useCallback((index: number) => {
    const item = items[index];
    if (item) act.mutate({ trackId: item.track.id, action: "reject" });
  }, [items, act]);

  // Keep the selection in range as reviewed rows leave the list.
  const current = Math.min(selected, Math.max(0, items.length - 1));

  useEffect(() => {
    if (status !== "PENDING") return;
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      const item = items[current];
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        setSelected(Math.min(current + 1, items.length - 1));
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        setSelected(Math.max(current - 1, 0));
      } else if (event.key === "Enter" && item?.suggestions[0]) {
        approve(current, item.suggestions[0].genre);
      } else if (/^[1-4]$/.test(event.key) && item?.suggestions[Number(event.key) - 1]) {
        approve(current, item.suggestions[Number(event.key) - 1].genre);
      } else if (event.key === "r") {
        reject(current);
      } else if (event.key === "p" && item) {
        usePlayer.getState().play(item.track, (item.track.duration_ms ?? 0) / 3000);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [status, items, current, approve, reject]);

  useEffect(() => {
    document.querySelector(`[data-review-index="${current}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  const folderBacked = items.filter((i) => i.suggestions[0]?.source.includes("FOLDER"));

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-border px-4 py-3">
        <div className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.status}
              type="button"
              onClick={() => {
                setStatus(tab.status);
                setPage(0);
                setSelected(0);
              }}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
                status === tab.status && "bg-muted text-foreground",
              )}
            >
              {tab.label}
              <span className="font-mono text-[11px] tabular-nums opacity-70">{counts?.[tab.status] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto">
          <JobControl
            id="genres"
            status={api.analysisStatus}
            start={api.startAnalysis}
            stop={api.stopAnalysis}
            invalidate={GENRE_JOB_REFRESH}
            label="Analyse library"
            icon={<AudioWaveform />}
            hint="Suggest genres from your folders, then from the audio (≈1.5 s per track)"
          />
        </div>
      </header>

      {status === "PENDING" && items.length > 0 && (
        <div className="flex items-center gap-3 border-b border-border px-4 py-2 text-[11px] text-muted-foreground">
          <span>
            <kbd className="font-mono">J/K</kbd> move · <kbd className="font-mono">Enter</kbd> approve top · <kbd className="font-mono">1–4</kbd> pick ·{" "}
            <kbd className="font-mono">R</kbd> reject · <kbd className="font-mono">P</kbd> play
          </span>
          {folderBacked.length > 0 && (
            <ConfirmButton
              size="xs"
              variant="outline"
              className="ml-auto"
              disabled={bulk.isPending}
              onConfirm={() => bulk.mutate(folderBacked.map((i) => i.track.id))}
              confirmLabel={`Confirm: approve ${folderBacked.length} tracks`}
            >
              Approve the {folderBacked.length} folder-based suggestions on this page
            </ConfirmButton>
          )}
        </div>
      )}

      <ErrorNotice error={reviews.error} action="Loading the review queue" />
      <ErrorNotice error={act.error ?? bulk.error} action="Saving the review" />

      <datalist id="genre-vocabulary">
        {facets.data?.genres.map((g) => <option key={g.value} value={g.value} />)}
      </datalist>

      <div className="min-h-0 flex-1 overflow-auto" role="table" aria-label="Genre suggestions">
        {items.map((item, index) => (
          <div key={item.track.id} data-review-index={index}>
            <ReviewRow
              item={item}
              selected={status === "PENDING" && index === current}
              onSelect={() => setSelected(index)}
              onApprove={(genre) => approve(index, genre)}
              onReject={() => reject(index)}
              onReset={() => act.mutate({ trackId: item.track.id, action: "reset" })}
            />
          </div>
        ))}
        {!reviews.isLoading && !reviews.isError && items.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 py-20 text-center text-sm text-muted-foreground">
            {status === "PENDING" ? (
              <>
                <p>Nothing to review.</p>
                <p className="max-w-md text-xs">
                  &ldquo;Analyse library&rdquo; suggests a genre for every track: first from your folders (02_GENRES/HOUSE/TECH_HOUSE →
                  Tech House), then from the audio with Essentia&apos;s Discogs model. Nothing is written until you approve.
                </p>
              </>
            ) : (
              <p>No {status.toLowerCase()} tracks yet.</p>
            )}
          </div>
        )}
      </div>

      {pages > 1 && (
        <footer className="flex items-center justify-center gap-3 border-t border-border py-2 text-xs text-muted-foreground">
          <Button variant="ghost" size="xs" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span className="font-mono tabular-nums">
            {page + 1} / {pages}
          </span>
          <Button variant="ghost" size="xs" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </footer>
      )}
    </div>
  );
}
