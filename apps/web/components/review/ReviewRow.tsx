"use client";

import type { GenreSuggestion, ReviewItem } from "@cueflow/types";
import { AudioWaveform, Check, Folder, Pause, Play, RotateCcw, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatBpm, trackTitle } from "@/lib/format";
import { usePlayer } from "@/lib/player";
import { cn } from "@/lib/utils";

interface ReviewRowProps {
  item: ReviewItem;
  selected: boolean;
  onSelect: () => void;
  onApprove: (genre: string) => void;
  onReject: () => void;
  onReset: () => void;
}

function SourceIcon({ source }: { source: GenreSuggestion["source"] }) {
  return (
    <span className="flex items-center gap-0.5 opacity-70" title={source === "AUDIO" ? "Audio model" : source === "FOLDER" ? "Your folder" : "Folder and audio agree"}>
      {source.includes("FOLDER") && <Folder className="size-3" />}
      {source.includes("AUDIO") && <AudioWaveform className="size-3" />}
    </span>
  );
}

export function ReviewRow({ item, selected, onSelect, onApprove, onReject, onReset }: ReviewRowProps) {
  const { track, suggestions, review, folder } = item;
  const [custom, setCustom] = useState("");
  const isCurrent = usePlayer((s) => s.track?.id === track.id);
  const playing = usePlayer((s) => s.playing && s.track?.id === track.id);
  const pending = review.status === "PENDING";

  return (
    <div
      role="row"
      aria-selected={selected}
      onClick={onSelect}
      className={cn(
        "grid grid-cols-[2rem_minmax(0,16rem)_minmax(0,1fr)_auto] items-center gap-4 border-b border-border/40 px-4 py-2.5",
        selected ? "bg-primary/10" : "hover:bg-muted/40",
      )}
    >
      <button
        type="button"
        aria-label={playing ? "Pause" : `Play ${trackTitle(track)}`}
        onClick={(event) => {
          event.stopPropagation();
          if (isCurrent) usePlayer.getState().toggle();
          else usePlayer.getState().play(track, (track.duration_ms ?? 0) / 3000);
        }}
        className="flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-primary hover:text-primary-foreground"
      >
        {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
      </button>

      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{trackTitle(track)}</div>
        <div className="truncate text-xs text-muted-foreground">
          {track.artist ?? "Unknown artist"} · <span className="font-mono">{formatBpm(track.bpm)}</span>
        </div>
        <div className="truncate text-[11px] text-muted-foreground/70" title={folder}>
          {folder.replaceAll(":", "/")}
        </div>
      </div>

      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="text-[11px] text-muted-foreground">
          Current: <span className="text-foreground">{track.genre ?? "—"}</span>
          {review.status === "APPROVED" && review.previous_genre !== review.chosen_genre && (
            <span> (was {review.previous_genre ?? "empty"})</span>
          )}
        </div>
        {pending ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {suggestions.map((s, index) => (
              <button
                key={s.genre}
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onApprove(s.genre);
                }}
                title={`Approve "${s.genre}" (key ${index + 1})`}
                className={cn(
                  "flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground",
                  index === 0 ? "border-primary/60 text-foreground" : "border-border text-muted-foreground",
                )}
              >
                <span className="font-mono text-[10px] opacity-50">{index + 1}</span>
                {s.genre}
                {s.confidence != null && <span className="font-mono text-[10px] opacity-60">{Math.round(s.confidence * 100)}%</span>}
                <SourceIcon source={s.source} />
              </button>
            ))}
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (custom.trim()) onApprove(custom.trim());
                setCustom("");
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <Input value={custom} onChange={(event) => setCustom(event.target.value)} list="genre-vocabulary" placeholder="Other genre…" className="h-7 w-32 text-xs" aria-label="Other genre" />
            </form>
          </div>
        ) : (
          <div className="text-xs">
            {review.status === "APPROVED" ? (
              <span className="text-primary">✓ {review.chosen_genre}</span>
            ) : (
              <span className="text-muted-foreground">✗ Rejected — genre left unchanged</span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1" onClick={(event) => event.stopPropagation()}>
        {pending ? (
          <>
            <Button size="sm" disabled={!suggestions.length} onClick={() => suggestions[0] && onApprove(suggestions[0].genre)} title="Approve top suggestion (Enter)">
              <Check /> Approve
            </Button>
            <Button variant="ghost" size="sm" onClick={onReject} title="Reject (R)">
              <X /> Reject
            </Button>
          </>
        ) : (
          <Button variant="ghost" size="sm" onClick={onReset} title="Back to the queue, original genre restored">
            <RotateCcw /> Undo
          </Button>
        )}
      </div>
    </div>
  );
}
