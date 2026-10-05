"use client";

import type { EditList, EditSegment } from "@cueflow/types";
import { create } from "zustand";

import type { FrameRange } from "@/lib/editor";

const HISTORY_LIMIT = 200;

interface EditorState {
  trackId: string | null;
  edit: EditList | null;
  /** JSON of the last saved (or loaded) edit: the working edit is dirty when it differs. */
  savedJson: string | null;
  past: EditList[];
  future: EditList[];
  /** Consecutive changes with the same key (a gain slider drag) make a single undo step. */
  lastKey: string | null;
  selection: FrameRange | null;
  clipboard: EditSegment[] | null;

  load: (trackId: string, edit: EditList, saved: EditList | null) => void;
  /** Apply an edit operation as one undoable step. */
  apply: (edit: EditList, key?: string) => void;
  undo: () => void;
  redo: () => void;
  select: (selection: FrameRange | null) => void;
  setClipboard: (clip: EditSegment[]) => void;
  markSaved: (saved: EditList | null) => void;
}

export const useEditor = create<EditorState>((set, get) => ({
  trackId: null,
  edit: null,
  savedJson: null,
  past: [],
  future: [],
  lastKey: null,
  selection: null,
  clipboard: null,

  load: (trackId, edit, saved) =>
    set({
      trackId,
      edit,
      savedJson: saved ? JSON.stringify(saved) : null,
      past: [],
      future: [],
      lastKey: null,
      selection: null,
      // The clipboard holds frames of one original: it does not follow to another track.
      clipboard: get().trackId === trackId ? get().clipboard : null,
    }),

  apply: (edit, key) => {
    const { edit: current, past, lastKey } = get();
    if (!current) return;
    const coalesce = key !== undefined && key === lastKey;
    set({
      edit,
      past: coalesce ? past : [...past, current].slice(-HISTORY_LIMIT),
      future: [],
      lastKey: key ?? null,
    });
  },

  undo: () => {
    const { edit, past, future } = get();
    const previous = past.at(-1);
    if (!edit || !previous) return;
    set({ edit: previous, past: past.slice(0, -1), future: [edit, ...future], lastKey: null, selection: null });
  },

  redo: () => {
    const { edit, past, future } = get();
    const [next, ...rest] = future;
    if (!edit || !next) return;
    set({ edit: next, past: [...past, edit], future: rest, lastKey: null, selection: null });
  },

  select: (selection) => set({ selection: selection && selection.end > selection.start ? selection : null }),
  setClipboard: (clipboard) => set({ clipboard }),
  markSaved: (saved) => set({ savedJson: saved ? JSON.stringify(saved) : null, lastKey: null }),
}));
