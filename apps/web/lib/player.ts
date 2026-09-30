"use client";

import type { Track } from "@cueflow/types";
import { create } from "zustand";

import { api } from "@/lib/api";

interface PlayerState {
  track: Track | null;
  queue: Track[];
  playing: boolean;
  time: number;
  duration: number;
  /** Load `track` (optionally at `startAt` seconds) and play it; `queue` enables next/previous. */
  play: (track: Track, startAt?: number, queue?: Track[]) => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  step: (direction: 1 | -1) => void;
  /** Keep the playing track in sync after an edit (rating, tags...). */
  refresh: (track: Track) => void;
}

let audio: HTMLAudioElement | null = null;

/** The single <audio> element shared by the player bar and every waveform. */
export function getAudio(): HTMLAudioElement {
  if (audio) return audio;
  audio = new Audio();
  audio.preload = "auto";
  audio.crossOrigin = "anonymous";
  audio.addEventListener("play", () => usePlayer.setState({ playing: true }));
  audio.addEventListener("pause", () => usePlayer.setState({ playing: false }));
  audio.addEventListener("timeupdate", () => usePlayer.setState({ time: audio!.currentTime }));
  audio.addEventListener("loadedmetadata", () => usePlayer.setState({ duration: audio!.duration }));
  audio.addEventListener("ended", () => usePlayer.getState().step(1));
  return audio;
}

export const usePlayer = create<PlayerState>((set, get) => ({
  track: null,
  queue: [],
  playing: false,
  time: 0,
  duration: 0,

  play: (track, startAt = 0, queue) => {
    const element = getAudio();
    const url = api.audioUrl(track.id);
    if (get().track?.id !== track.id || element.src !== url) {
      element.src = url;
      set({ track, time: startAt, duration: (track.duration_ms ?? 0) / 1000 });
    }
    if (queue) set({ queue });
    element.currentTime = startAt;
    void element.play().catch(() => set({ playing: false }));
  },

  toggle: () => {
    const { track } = get();
    if (!track) return;
    const element = getAudio();
    if (element.paused) void element.play();
    else element.pause();
  },

  seek: (seconds) => {
    if (get().track) getAudio().currentTime = seconds;
  },

  step: (direction) => {
    const { queue, track } = get();
    const index = queue.findIndex((t) => t.id === track?.id);
    const next = index === -1 ? undefined : queue[index + direction];
    if (next) get().play(next);
    else if (direction === -1) get().seek(0);
  },

  refresh: (updated) => {
    set((state) => ({
      track: state.track?.id === updated.id ? updated : state.track,
      queue: state.queue.map((t) => (t.id === updated.id ? updated : t)),
    }));
  },
}));
