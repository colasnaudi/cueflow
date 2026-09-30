"use client";

import type { Track, TrackPage, TrackUpdate } from "@cueflow/types";
import { type InfiniteData, type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { usePlayer } from "@/lib/player";

/** Write an updated track into every cache that holds it, instead of refetching whole lists. */
export function applyTrackUpdate(client: QueryClient, track: Track) {
  client.setQueryData(["track", track.id], track);
  client.setQueriesData<InfiniteData<TrackPage>>({ queryKey: ["tracks"] }, (data) =>
    data && {
      ...data,
      pages: data.pages.map((page) => ({ ...page, items: page.items.map((t) => (t.id === track.id ? track : t)) })),
    },
  );
  usePlayer.getState().refresh(track);
}

export function useTrackMutations(trackId: string) {
  const client = useQueryClient();
  const onSuccess = (track: Track) => applyTrackUpdate(client, track);
  // Tag lists and tag filters depend on counts: refresh them after tag changes.
  const onTagsChanged = (track: Track) => {
    onSuccess(track);
    void client.invalidateQueries({ queryKey: ["tags"] });
  };

  return {
    update: useMutation({ mutationFn: (body: TrackUpdate) => api.updateTrack(trackId, body), onSuccess }),
    addTag: useMutation({ mutationFn: (name: string) => api.addTag(trackId, name), onSuccess: onTagsChanged }),
    removeTag: useMutation({ mutationFn: (tagId: string) => api.removeTag(trackId, tagId), onSuccess: onTagsChanged }),
  };
}
