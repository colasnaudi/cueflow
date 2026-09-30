"use client";

import type { Track } from "@cueflow/types";
import { Pause, Play } from "lucide-react";
import Link from "next/link";
import { memo } from "react";

import { KeyBadge } from "@/components/library/KeyBadge";
import { Rating } from "@/components/library/Rating";
import { formatBpm, formatDuration, trackTitle } from "@/lib/format";
import { useTrackMutations } from "@/lib/mutations";
import { usePlayer } from "@/lib/player";
import { cn } from "@/lib/utils";

export const TRACK_GRID = "grid grid-cols-[2.25rem_minmax(0,1fr)_9rem_3.5rem_3.5rem_3.5rem_5.5rem_minmax(0,9rem)] items-center gap-3";

interface TrackRowProps {
  track: Track;
  index: number;
  onPlay: (track: Track) => void;
}

export const TrackRow = memo(function TrackRow({ track, index, onPlay }: TrackRowProps) {
  const isCurrent = usePlayer((s) => s.track?.id === track.id);
  const playing = usePlayer((s) => s.playing && s.track?.id === track.id);
  const { update } = useTrackMutations(track.id);

  return (
    <div
      role="row"
      onDoubleClick={() => onPlay(track)}
      className={cn(TRACK_GRID, "group h-11 border-b border-border/40 px-4 text-sm hover:bg-muted/40", isCurrent && "bg-primary/10 hover:bg-primary/15")}
    >
      <button
        type="button"
        aria-label={playing ? "Pause" : `Play ${trackTitle(track)}`}
        onClick={() => (isCurrent ? usePlayer.getState().toggle() : onPlay(track))}
        className="flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-primary hover:text-primary-foreground"
      >
        {playing ? (
          <Pause className="size-3.5" />
        ) : (
          <>
            <Play className={cn("size-3.5", !isCurrent && "hidden group-hover:block")} />
            {!isCurrent && <span className="font-mono text-[11px] tabular-nums group-hover:hidden">{index + 1}</span>}
          </>
        )}
      </button>

      <div className="min-w-0">
        <Link href={`/tracks/${track.id}`} className={cn("block truncate font-medium hover:underline", isCurrent && "text-primary")}>
          {trackTitle(track)}
        </Link>
        <div className="truncate text-xs text-muted-foreground">{track.artist ?? "Unknown artist"}</div>
      </div>

      <div className="truncate text-xs text-muted-foreground">{track.genre ?? ""}</div>
      <div className="text-right font-mono text-xs tabular-nums">{formatBpm(track.bpm)}</div>
      <div>
        <KeyBadge camelot={track.camelot_key} />
      </div>
      <div className="text-right font-mono text-xs tabular-nums text-muted-foreground">{formatDuration(track.duration_ms)}</div>
      <Rating value={track.rating} onChange={(rating) => update.mutate({ rating })} />
      <div className="flex min-w-0 gap-1 overflow-hidden">
        {track.tags.map((tag) => (
          <span key={tag.id} className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            #{tag.name}
          </span>
        ))}
      </div>
    </div>
  );
});
