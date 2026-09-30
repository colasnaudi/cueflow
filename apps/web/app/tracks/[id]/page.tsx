"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Pause, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use } from "react";

import { AnalysisPanel } from "@/components/analysis/AnalysisPanel";
import { BeatgridOverlay } from "@/components/analysis/BeatgridOverlay";
import { KeyBadge } from "@/components/library/KeyBadge";
import { Rating } from "@/components/library/Rating";
import { TagEditor } from "@/components/library/TagEditor";
import { Waveform } from "@/components/player/Waveform";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatBpm, formatDuration, trackTitle } from "@/lib/format";
import { useTrackMutations } from "@/lib/mutations";
import { usePlayer } from "@/lib/player";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">{label}</dt>
      <dd className="truncate text-sm">{children ?? <span className="text-muted-foreground">–</span>}</dd>
    </div>
  );
}

export default function TrackPage({ params }: PageProps<"/tracks/[id]">) {
  const { id } = use(params);
  const router = useRouter();
  const { data: track, isError, error } = useQuery({ queryKey: ["track", id], queryFn: () => api.track(id) });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const analysis = useQuery({ queryKey: ["analysis", id], queryFn: () => api.trackAnalysis(id) });
  const { update, addTag, removeTag } = useTrackMutations(id);
  const isCurrent = usePlayer((s) => s.track?.id === id);
  const playing = usePlayer((s) => s.playing && s.track?.id === id);

  if (isError) return <p className="p-8 text-sm text-destructive">{error.message}</p>;
  if (!track) return <p className="p-8 text-sm text-muted-foreground">Loading…</p>;

  const format = track.filename.split(".").pop()?.toUpperCase();

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-8 py-6">
        <button type="button" onClick={() => router.back()} className="flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Library
        </button>

        <header className="flex items-end gap-5">
          <Button
            size="icon-lg"
            className="size-14 rounded-full"
            aria-label={playing ? "Pause" : "Play"}
            onClick={() => (isCurrent ? usePlayer.getState().toggle() : usePlayer.getState().play(track))}
          >
            {playing ? <Pause className="size-6" /> : <Play className="size-6" />}
          </Button>
          <div className="min-w-0 flex-1">
            <Link href={`/library?q=${encodeURIComponent(track.artist ?? "")}`} className="text-sm font-medium tracking-wider text-muted-foreground uppercase hover:text-foreground">
              {track.artist ?? "Unknown artist"}
            </Link>
            <h1 className="truncate text-3xl font-semibold tracking-tight">{trackTitle(track)}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-sm tabular-nums">
              <span>{formatBpm(track.bpm)} BPM</span>
              <KeyBadge camelot={track.camelot_key} />
              {track.musical_key && <span className="text-muted-foreground">{track.musical_key}</span>}
              {track.genre && <span className="font-sans text-muted-foreground">{track.genre}</span>}
              <span className="text-muted-foreground">{formatDuration(track.duration_ms)}</span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Rating value={track.rating} size="md" onChange={(rating) => update.mutate({ rating })} />
            <Badge variant="outline" className="font-mono text-[10px]">
              {track.status.replace("_", " ")}
            </Badge>
          </div>
        </header>

        <section className="rounded-lg border border-border bg-card px-4 py-5">
          <Waveform
            track={track}
            height={128}
            overlay={(duration) => analysis.data && <BeatgridOverlay analysis={analysis.data} duration={duration} />}
          />
        </section>

        <AnalysisPanel track={track} analysis={analysis.data} />

        <section className="flex flex-col gap-2">
          <h2 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Tags</h2>
          <TagEditor
            tags={track.tags}
            suggestions={tags.data}
            onAdd={(name) => addTag.mutate(name)}
            onRemove={(tagId) => removeTag.mutate(tagId)}
            pending={addTag.isPending}
          />
        </section>

        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 border-t border-border pt-6 md:grid-cols-4">
          <Field label="Album">{track.album}</Field>
          <Field label="Label">{track.label}</Field>
          <Field label="Year">{track.year}</Field>
          <Field label="Format">
            {format} {track.bitrate && `· ${track.bitrate} kbps`} {track.sample_rate && `· ${(track.sample_rate / 1000).toFixed(1)} kHz`}
          </Field>
          <div className="col-span-full">
            <Field label="File">
              <span className="font-mono text-xs text-muted-foreground">{track.path}</span>
            </Field>
          </div>
        </dl>
      </div>
    </div>
  );
}
