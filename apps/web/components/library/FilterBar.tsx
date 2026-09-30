"use client";

import type { Facets, TagCount, TrackQuery } from "@cueflow/types";
import { Disc3, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { camelotColor, compatibleKeys } from "@/lib/format";
import { usePlayer } from "@/lib/player";
import { cn } from "@/lib/utils";

type Update = (changes: Record<string, string | string[] | number | undefined>) => void;

interface FilterBarProps {
  query: TrackQuery;
  facets: Facets | undefined;
  tags: TagCount[] | undefined;
  showSamples: boolean;
  showDuplicates: boolean;
  update: Update;
}

const KEY_ROWS = ["A", "B"].map((letter) => Array.from({ length: 12 }, (_, i) => `${i + 1}${letter}`));

function Chip({ active, onClick, children, className }: { active: boolean; onClick: () => void; children: React.ReactNode; className?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "h-6 shrink-0 rounded-md border px-2 text-xs transition-colors",
        active ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
        className,
      )}
    >
      {children}
    </button>
  );
}

function toggle(list: string[] | undefined, value: string) {
  const current = list ?? [];
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
}

function BpmInput({ value, placeholder, onCommit }: { value: number | undefined; placeholder: string; onCommit: (v: string) => void }) {
  const [draft, setDraft] = useState(value?.toString() ?? "");
  const [committed, setCommitted] = useState(value);
  if (value !== committed) {
    setCommitted(value);
    setDraft(value?.toString() ?? "");
  }
  return (
    <Input
      inputMode="decimal"
      value={draft}
      placeholder={placeholder}
      onChange={(event) => setDraft(event.target.value.replace(/[^\d.]/g, ""))}
      onBlur={() => onCommit(draft)}
      onKeyDown={(event) => event.key === "Enter" && onCommit(draft)}
      className="h-6 w-14 px-1.5 text-center font-mono text-xs"
      aria-label={`BPM ${placeholder}`}
    />
  );
}

export function FilterBar({ query, facets, tags, showSamples, showDuplicates, update }: FilterBarProps) {
  const current = usePlayer((s) => s.track);
  const usedTags = tags?.filter((tag) => tag.count > 0 || query.tag?.includes(tag.name));
  const keyCounts = new Map(facets?.keys.map((k) => [k.value, k.count]));
  const hasFilters =
    !!query.genre?.length || !!query.key?.length || !!query.tag?.length || query.bpm_min != null || query.bpm_max != null || !!query.rating_min;

  const matchCurrent = () => {
    if (!current) return;
    update({
      key: current.camelot_key ? compatibleKeys(current.camelot_key) : undefined,
      bpm_min: current.bpm ? Math.floor(current.bpm * 0.97) : undefined,
      bpm_max: current.bpm ? Math.ceil(current.bpm * 1.03) : undefined,
      genre: undefined,
    });
  };

  return (
    <div className="flex flex-col gap-2.5 border-b border-border px-4 py-3">
      <div className="flex items-center gap-1.5 overflow-x-auto">
        <Chip active={!query.genre?.length} onClick={() => update({ genre: undefined })}>
          All
        </Chip>
        {facets?.genres.slice(0, 14).map((genre) => (
          <Chip key={genre.value} active={!!query.genre?.includes(genre.value)} onClick={() => update({ genre: toggle(query.genre, genre.value) })}>
            {genre.value} <span className="opacity-60">{genre.count}</span>
          </Chip>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">BPM</span>
          <BpmInput value={query.bpm_min} placeholder="min" onCommit={(v) => update({ bpm_min: v })} />
          <span className="text-muted-foreground">–</span>
          <BpmInput value={query.bpm_max} placeholder="max" onCommit={(v) => update({ bpm_max: v })} />
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Key</span>
          <div className="grid grid-cols-12 gap-px">
            {KEY_ROWS.flat().map((key) => {
              const active = !!query.key?.includes(key);
              const count = keyCounts.get(key) ?? 0;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => update({ key: toggle(query.key, key) })}
                  aria-pressed={active}
                  title={`${key} · ${count} tracks`}
                  disabled={!count && !active}
                  className={cn(
                    "h-4 w-7 rounded-sm font-mono text-[9px] leading-4 transition-opacity disabled:opacity-20",
                    active ? "font-bold text-black" : "text-black/70 opacity-45 hover:opacity-80",
                  )}
                  style={{ backgroundColor: camelotColor(key) }}
                >
                  {key}
                </button>
              );
            })}
          </div>
        </div>

        <Button variant="outline" size="xs" onClick={matchCurrent} disabled={!current} title="Compatible keys and ±3% BPM of the playing track">
          <Disc3 /> Match playing
        </Button>

        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Rating</span>
          {[3, 4, 5].map((stars) => (
            <Chip key={stars} active={query.rating_min === stars} onClick={() => update({ rating_min: query.rating_min === stars ? undefined : stars })}>
              {stars}★+
            </Chip>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          <Chip active={showSamples} onClick={() => update({ samples: showSamples ? undefined : "1" })}>
            Samples &lt;60s
          </Chip>
          <Chip active={showDuplicates} onClick={() => update({ duplicates: showDuplicates ? undefined : "1" })}>
            Duplicates
          </Chip>
          {hasFilters && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => update({ genre: undefined, key: undefined, tag: undefined, bpm_min: undefined, bpm_max: undefined, rating_min: undefined })}
            >
              <X /> Clear
            </Button>
          )}
        </div>
      </div>

      {!!usedTags?.length && (
        <div className="flex items-center gap-1.5 overflow-x-auto">
          <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Tags</span>
          {usedTags.map((tag) => (
            <Chip key={tag.id} active={!!query.tag?.includes(tag.name)} onClick={() => update({ tag: toggle(query.tag, tag.name) })}>
              #{tag.name} <span className="opacity-60">{tag.count}</span>
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}
