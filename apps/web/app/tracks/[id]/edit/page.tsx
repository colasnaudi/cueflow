"use client";

import { useQuery } from "@tanstack/react-query";
import { use, useEffect, useState } from "react";
import { toast } from "sonner";

import { Editor } from "@/components/editor/Editor";
import { api } from "@/lib/api";
import { identityEdit } from "@/lib/editor";
import { EditorEngine } from "@/lib/editor-audio";
import { useEditor } from "@/lib/editor-store";
import { getAudio } from "@/lib/player";

type Loaded = { original: AudioBuffer; engine: EditorEngine };

/** Decode the original (served already decoded by the API, so preview and export use the same samples). */
async function loadSource(trackId: string, sampleRate: number): Promise<Loaded> {
  const response = await fetch(api.editSourceUrl(trackId));
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${response.status} ${response.statusText}`);
  }
  const context = new AudioContext({ sampleRate });
  const original = await context.decodeAudioData(await response.arrayBuffer());
  return { original, engine: new EditorEngine(context, original, original) };
}

export default function EditPage({ params }: PageProps<"/tracks/[id]/edit">) {
  const { id } = use(params);
  const track = useQuery({ queryKey: ["track", id], queryFn: () => api.track(id) });
  const saved = useQuery({ queryKey: ["edit", id], queryFn: () => api.trackEdit(id), staleTime: 0, gcTime: 0 });
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ready = useEditor((s) => s.trackId === id && s.edit !== null) && loaded !== null;

  // The editor has its own playback: the shared player stops while it is open.
  useEffect(() => getAudio().pause(), []);

  useEffect(() => {
    if (!saved.data) return;
    const { sample_rate: sampleRate, edit } = saved.data;
    let cancelled = false;
    let result: Loaded | null = null;
    loadSource(id, sampleRate)
      .then((source) => {
        result = source;
        if (cancelled) return source.engine.dispose();
        const frames = source.original.length;
        const fits = edit && edit.sample_rate === sampleRate && edit.segments.every((s) => s.end <= frames);
        if (edit && !fits) toast.error("The saved edit no longer matches the audio file: starting from the original");
        useEditor.getState().load(id, fits ? edit : identityEdit(sampleRate, frames), fits ? edit : null);
        setLoaded(source);
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => {
      cancelled = true;
      result?.engine.dispose();
    };
  }, [id, saved.data]);

  const failure = track.error?.message ?? saved.error?.message ?? error;
  if (failure) return <p className="p-8 text-sm text-destructive">Cannot open the editor: {failure}</p>;
  if (!track.data || !loaded || !ready) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
        <span className="h-px w-48 animate-pulse bg-muted-foreground/40" />
        Decoding the original…
      </div>
    );
  }
  return <Editor track={track.data} original={loaded.original} engine={loaded.engine} />;
}
