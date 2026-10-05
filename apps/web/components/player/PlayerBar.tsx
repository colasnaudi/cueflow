"use client";

import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { KeyBadge } from "@/components/library/KeyBadge";
import { Waveform } from "@/components/player/Waveform";
import { Button } from "@/components/ui/button";
import { formatBpm, formatTime, trackTitle } from "@/lib/format";
import { usePlayer } from "@/lib/player";

function isTyping(target: EventTarget | null) {
  return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
}

export function PlayerBar() {
  const { track, playing, time, duration, toggle, step } = usePlayer();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey) return;
      if (window.location.pathname.endsWith("/edit")) return; // the editor has its own transport
      if (event.code === "Space") {
        event.preventDefault();
        usePlayer.getState().toggle();
      } else if (event.key === "ArrowRight" && event.shiftKey) {
        usePlayer.getState().step(1);
      } else if (event.key === "ArrowLeft" && event.shiftKey) {
        usePlayer.getState().step(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!track) {
    return (
      <footer className="flex h-16 items-center border-t border-border px-4 text-xs text-muted-foreground">
        Double-click a track to play it · Space to play/pause · Shift+←/→ previous/next
      </footer>
    );
  }

  return (
    <footer className="grid h-16 grid-cols-[minmax(0,16rem)_auto_minmax(0,1fr)_auto] items-center gap-4 border-t border-border px-4">
      <Link href={`/tracks/${track.id}`} className="min-w-0 hover:underline">
        <div className="truncate text-sm font-medium">{trackTitle(track)}</div>
        <div className="truncate text-xs text-muted-foreground">{track.artist ?? "Unknown artist"}</div>
      </Link>

      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon-sm" aria-label="Previous" onClick={() => step(-1)}>
          <SkipBack />
        </Button>
        <Button size="icon" aria-label={playing ? "Pause" : "Play"} onClick={toggle}>
          {playing ? <Pause /> : <Play />}
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Next" onClick={() => step(1)}>
          <SkipForward />
        </Button>
      </div>

      <div className="flex min-w-0 items-center gap-3">
        <span className="w-10 text-right font-mono text-xs tabular-nums text-muted-foreground">{formatTime(time)}</span>
        <Waveform track={track} height={40} className="min-w-0 flex-1" />
        <span className="w-10 font-mono text-xs tabular-nums text-muted-foreground">{formatTime(duration)}</span>
      </div>

      <div className="flex items-center gap-2 font-mono text-xs tabular-nums">
        <span>{formatBpm(track.bpm)} BPM</span>
        <KeyBadge camelot={track.camelot_key} />
      </div>
    </footer>
  );
}
