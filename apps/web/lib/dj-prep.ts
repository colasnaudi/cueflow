"use client";

import type { Anchor, Annotation, AnnotationInput, Cue, CueChanges, CueInput, SectionInput, TrackAnalysis } from "@cueflow/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { BEATS_PER_BAR, TempoMap } from "@/lib/tempo";

export const MIN_BPM = 40;
export const MAX_BPM = 250;

/** Rekordbox's hot cue palette. */
export const CUE_COLORS = ["#E62828", "#FFA000", "#FFD300", "#28E214", "#10B1C8", "#305AFF", "#AA72FF", "#8C8C8C"];

export const CUE_PRESETS = ["START", "GROOVE", "BREAK", "BUILD", "DROP", "VOCAL", "OUTRO"] as const;

export const LOOP_LENGTHS = [0.5, 1, 2, 4, 8, 16, 32];

/** Camelot -> musical key, as DJ software shows it. */
export const CAMELOT_KEYS: [string, string][] = [
  ["1A", "A♭ minor"], ["1B", "B major"], ["2A", "E♭ minor"], ["2B", "F♯ major"],
  ["3A", "B♭ minor"], ["3B", "D♭ major"], ["4A", "F minor"], ["4B", "A♭ major"],
  ["5A", "C minor"], ["5B", "E♭ major"], ["6A", "G minor"], ["6B", "B♭ major"],
  ["7A", "D minor"], ["7B", "F major"], ["8A", "A minor"], ["8B", "C major"],
  ["9A", "E minor"], ["9B", "G major"], ["10A", "B minor"], ["10B", "D major"],
  ["11A", "F♯ minor"], ["11B", "A major"], ["12A", "D♭ minor"], ["12B", "E major"],
]; // prettier-ignore

/** Server state of the DJ preparation (analysis, cues, notes) and its mutations, cache updated in place. */
export function useDjPrep(trackId: string) {
  const client = useQueryClient();
  const analysis = useQuery({ queryKey: ["analysis", trackId], queryFn: () => api.trackAnalysis(trackId) });
  const cues = useQuery({ queryKey: ["cues", trackId], queryFn: () => api.cues(trackId) });
  const notes = useQuery({ queryKey: ["annotations", trackId], queryFn: () => api.annotations(trackId) });

  const onError = (error: Error) => toast.error(error.message);
  const setAnalysis = (data: TrackAnalysis) => {
    client.setQueryData(["analysis", trackId], data);
    void client.invalidateQueries({ queryKey: ["track", trackId] }); // the grid sets the BPM
  };
  const setCues = (data: Cue[]) => client.setQueryData(["cues", trackId], data);
  const setNotes = (data: Annotation[]) => client.setQueryData(["annotations", trackId], data);

  return {
    analysis: analysis.data,
    cues: cues.data ?? [],
    notes: notes.data ?? [],
    saveGrid: useMutation({ mutationFn: (anchors: Anchor[]) => api.saveBeatgrid(trackId, anchors), onSuccess: setAnalysis, onError }),
    resetGrid: useMutation({ mutationFn: () => api.analyseTrack(trackId, true), onSuccess: setAnalysis, onError }),
    saveSections: useMutation({ mutationFn: (s: SectionInput[]) => api.saveSections(trackId, s), onSuccess: setAnalysis, onError }),
    restoreSections: useMutation({ mutationFn: () => api.restoreSections(trackId), onSuccess: setAnalysis, onError }),
    createCue: useMutation({ mutationFn: (body: CueInput) => api.createCue(trackId, body), onSuccess: setCues, onError }),
    editCue: useMutation({
      mutationFn: ({ id, changes }: { id: string; changes: CueChanges }) => api.editCue(trackId, id, changes),
      onSuccess: setCues,
      onError,
    }),
    deleteCue: useMutation({ mutationFn: (id: string) => api.deleteCue(trackId, id), onSuccess: setCues, onError }),
    createNote: useMutation({ mutationFn: (body: AnnotationInput) => api.createAnnotation(trackId, body), onSuccess: setNotes, onError }),
    editNote: useMutation({
      mutationFn: ({ id, changes }: { id: string; changes: Partial<AnnotationInput> }) => api.editAnnotation(trackId, id, changes),
      onSuccess: setNotes,
      onError,
    }),
    deleteNote: useMutation({ mutationFn: (id: string) => api.deleteAnnotation(trackId, id), onSuccess: setNotes, onError }),
  };
}

// --- Beatgrid edits: pure functions over the anchor list (a constant grid is one anchor). ---

const clampBpm = (bpm: number) => Math.round(Math.min(MAX_BPM, Math.max(MIN_BPM, bpm)) * 1000) / 1000;
const mod = (value: number, n: number) => ((value % n) + n) % n;

/** The anchor whose tempo is heard at `time`. */
export function segmentAt(anchors: Anchor[], time: number): number {
  let segment = 0;
  anchors.forEach((anchor, i) => time >= anchor.time && (segment = i));
  return segment;
}

export function withBpm(anchors: Anchor[], index: number, bpm: number): Anchor[] {
  return anchors.map((a, i) => (i === index ? { ...a, bpm: clampBpm(bpm) } : a));
}

/** Move the whole grid by `seconds` (earlier anchors never go below 0). */
export function nudged(anchors: Anchor[], seconds: number): Anchor[] {
  return anchors.map((a) => ({ ...a, time: Math.max(0, Math.round((a.time + seconds) * 10_000) / 10_000) }));
}

/** Bar 1 (a downbeat on a beat) exactly at `time`, in the tempo section heard there. */
export function barOneAt(anchors: Anchor[], time: number): Anchor[] {
  const index = segmentAt(anchors, time);
  return anchors.map((a, i) => (i === index ? { ...a, time: Math.max(0, time), beat: 1 } : a));
}

/** A tempo change on the beat nearest `time`, starting at the tempo heard there. */
export function withTempoChange(anchors: Anchor[], time: number): Anchor[] {
  const tempo = new TempoMap(anchors);
  const index = Math.round(tempo.indexOf(time));
  const at = tempo.timeOfIndex(index);
  if (anchors.some((a) => Math.abs(a.time - at) < 0.1)) throw new Error("There is already a tempo change here");
  const anchor = { time: Math.round(at * 10_000) / 10_000, bpm: tempo.bpmAt(at), beat: mod(index, BEATS_PER_BAR) + 1 };
  return [...anchors, anchor].sort((a, b) => a.time - b.time);
}

export function withoutAnchor(anchors: Anchor[], index: number): Anchor[] {
  return anchors.length > 1 ? anchors.filter((_, i) => i !== index) : anchors;
}

/** BPM from tap times (ms): the mean interval of the last taps, null until there are enough. */
export function tapBpm(taps: number[]): number | null {
  const recent = taps.slice(-8);
  if (recent.length < 4) return null;
  const interval = (recent.at(-1)! - recent[0]) / (recent.length - 1);
  return clampBpm(Math.round((60_000 / interval) * 100) / 100);
}
