"use client";

import type { SortField, Track, TrackQuery } from "@cueflow/types";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";

import { TRACK_GRID, TrackRow } from "@/components/library/TrackRow";
import { usePlayer } from "@/lib/player";
import { cn } from "@/lib/utils";

const COLUMNS: { label: string; sort?: SortField; align?: "right" }[] = [
  { label: "#" },
  { label: "Track", sort: "artist" },
  { label: "Genre", sort: "genre" },
  { label: "BPM", sort: "bpm", align: "right" },
  { label: "Key", sort: "key" },
  { label: "Time", sort: "duration", align: "right" },
  { label: "Rating", sort: "rating" },
  { label: "Tags" },
];

interface TrackTableProps {
  tracks: Track[];
  query: TrackQuery;
  onSort: (sort: SortField, order: "asc" | "desc") => void;
  hasMore: boolean;
  loadMore: () => void;
  loading: boolean;
}

export function TrackTable({ tracks, query, onSort, hasMore, loadMore, loading }: TrackTableProps) {
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver((entries) => entries[0]?.isIntersecting && loadMore(), { rootMargin: "600px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  // Rows are memoised: keep the callback stable and read the latest list through a ref.
  const tracksRef = useRef(tracks);
  useEffect(() => {
    tracksRef.current = tracks;
  }, [tracks]);
  const onPlay = useCallback((track: Track) => usePlayer.getState().play(track, 0, tracksRef.current), []);

  return (
    <div role="table" aria-rowcount={tracks.length} className="min-w-[56rem]">
      <div role="row" className={cn(TRACK_GRID, "sticky top-0 z-10 h-8 border-b border-border bg-background px-4 text-[11px] font-medium tracking-wider text-muted-foreground uppercase")}>
        {COLUMNS.map((column) => {
          const active = column.sort && query.sort === column.sort;
          const Arrow = query.order === "desc" ? ArrowDown : ArrowUp;
          return (
            <div key={column.label} role="columnheader" className={cn(column.align === "right" && "text-right")}>
              {column.sort ? (
                <button
                  type="button"
                  onClick={() => onSort(column.sort!, active && query.order === "asc" ? "desc" : "asc")}
                  className={cn("inline-flex items-center gap-1 uppercase hover:text-foreground", active && "text-foreground")}
                >
                  {column.label}
                  {active && <Arrow className="size-3" />}
                </button>
              ) : (
                column.label
              )}
            </div>
          );
        })}
      </div>

      {tracks.map((track, index) => (
        <TrackRow key={track.id} track={track} index={index} onPlay={onPlay} />
      ))}

      {!loading && tracks.length === 0 && <p className="px-4 py-16 text-center text-sm text-muted-foreground">No tracks match these filters.</p>}
      <div ref={sentinel} className="h-12 px-4 py-3 text-center text-xs text-muted-foreground">
        {loading && "Loading…"}
      </div>
    </div>
  );
}
