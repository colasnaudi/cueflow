"use client";

import type { Track } from "@cueflow/types";
import { Pause, Play } from "lucide-react";

import { usePlayer } from "@/lib/player";

export function MiniPlay({ track }: { track: Track }) {
  const isCurrent = usePlayer((s) => s.track?.id === track.id);
  const playing = usePlayer((s) => s.playing && s.track?.id === track.id);
  return (
    <button
      type="button"
      aria-label={playing ? "Pause" : `Play ${track.title ?? track.filename}`}
      onClick={() => (isCurrent ? usePlayer.getState().toggle() : usePlayer.getState().play(track))}
      className="flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-primary hover:text-primary-foreground"
    >
      {playing ? <Pause className="size-3" /> : <Play className="size-3" />}
    </button>
  );
}
