"use client";

import type { Track } from "@cueflow/types";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { getAudio, usePlayer } from "@/lib/player";

interface WaveformProps {
  track: Track;
  height?: number;
  className?: string;
  /** Drawn over the waveform, in a box whose width spans the whole track (`duration` seconds). */
  overlay?: (duration: number) => React.ReactNode;
}

/**
 * Server-computed peaks rendered by WaveSurfer. When `track` is the one loaded in the player, the waveform
 * drives the shared <audio> element; otherwise clicking it starts playback at that position.
 */
export function Waveform({ track, height = 96, className, overlay }: WaveformProps) {
  const container = useRef<HTMLDivElement>(null);
  const isCurrent = usePlayer((s) => s.track?.id === track.id);
  const { data, isError } = useQuery({
    queryKey: ["peaks", track.id],
    queryFn: () => api.peaks(track.id),
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!container.current || !data) return;
    const styles = getComputedStyle(document.documentElement);
    const ws = WaveSurfer.create({
      container: container.current,
      height,
      peaks: [data.peaks],
      duration: data.duration,
      waveColor: styles.getPropertyValue("--wave").trim() || "#555",
      progressColor: styles.getPropertyValue("--wave-progress").trim() || "#f59e0b",
      cursorColor: styles.getPropertyValue("--foreground").trim() || "#fff",
      cursorWidth: 1,
      barWidth: 2,
      barGap: 1,
      barRadius: 1,
      dragToSeek: true,
      ...(isCurrent ? { media: getAudio(), url: api.audioUrl(track.id) } : {}),
    });
    if (!isCurrent) {
      ws.on("interaction", (time) => usePlayer.getState().play(track, time));
    }
    return () => ws.destroy();
    // `track` identity changes on every refetch; the waveform only depends on its id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, height, isCurrent, track.id]);

  return (
    <div className={cn("relative w-full", className)} style={{ height }}>
      {!data && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
          {isError ? "Waveform unavailable" : <span className="h-px w-full animate-pulse bg-muted-foreground/30" />}
        </div>
      )}
      <div ref={container} className="h-full w-full cursor-pointer" />
      {data && overlay && <div className="pointer-events-none absolute inset-0 overflow-hidden">{overlay(data.duration)}</div>}
    </div>
  );
}
