"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AudioLines, Clock, Disc3, FolderSync, Library, ListMusic, Sparkles, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

import { JobControl } from "@/components/JobControl";
import { FolderTree } from "@/components/library/FolderTree";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const AUDIO_JOB_REFRESH = [["tracks"], ["track"], ["analysis"], ["facets"]];

const VIEWS = [
  {
    label: "All Tracks",
    href: "/library",
    icon: Library,
    match: (p: URLSearchParams) => !p.has("rating_min") && !p.has("folder") && p.get("sort") !== "added",
  },
  { label: "Recently Added", href: "/library?sort=added&order=desc", icon: Clock, match: (p: URLSearchParams) => p.get("sort") === "added" },
  { label: "Favorites", href: "/library?rating_min=4", icon: Star, match: (p: URLSearchParams) => p.get("rating_min") === "4" },
];

function Views() {
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    <nav className="flex flex-col gap-0.5">
      {VIEWS.map(({ label, href, icon: Icon, match }) => {
        const active = pathname === "/library" && match(params);
        return (
          <Link
            key={label}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
              active && "bg-muted text-foreground",
            )}
          >
            <Icon className="size-4" /> {label}
          </Link>
        );
      })}
    </nav>
  );
}

function Tools() {
  const pathname = usePathname();
  const { data } = useQuery({ queryKey: ["reviews", "counts"], queryFn: () => api.reviews("PENDING", 0, 1) });
  const pending = data?.counts.PENDING ?? 0;
  const tools = [
    { label: "Genre Review", href: "/review", icon: Sparkles, badge: pending || undefined },
    { label: "Cleanup", href: "/cleanup", icon: Trash2 },
    { label: "Rekordbox export", href: "/export", icon: Disc3 },
  ];
  return (
    <nav className="flex flex-col gap-0.5">
      {tools.map(({ label, href, icon: Icon, badge }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
            pathname === href && "bg-muted text-foreground",
          )}
        >
          <Icon className="size-4" /> {label}
          {badge !== undefined && (
            <span className="ml-auto rounded-full bg-primary px-1.5 font-mono text-[10px] leading-4 text-primary-foreground tabular-nums">
              {badge}
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}

function ScanButton() {
  const client = useQueryClient();
  const { data: status, refetch } = useQuery({
    queryKey: ["scan"],
    queryFn: api.scanStatus,
    refetchInterval: (query) => (query.state.data?.running ? 1000 : false),
  });
  const wasRunning = useRef(false);

  useEffect(() => {
    if (wasRunning.current && status && !status.running) {
      void client.invalidateQueries({ queryKey: ["tracks"] });
      void client.invalidateQueries({ queryKey: ["facets"] });
      void client.invalidateQueries({ queryKey: ["folders"] });
    }
    wasRunning.current = !!status?.running;
  }, [status, client]);

  const start = async () => {
    await api.startScan().catch(() => undefined);
    void refetch();
  };

  const running = !!status?.running;
  const progress = status?.total ? Math.round((status.processed / status.total) * 100) : 0;

  return (
    <div className="flex flex-col gap-1.5">
      <Button variant="outline" size="sm" onClick={start} disabled={running}>
        <FolderSync className={cn(running && "animate-spin")} /> {running ? `Scanning ${progress}%` : "Scan library"}
      </Button>
      {status?.state === "failed" && (
        <p className="text-[11px] leading-tight text-destructive" title={status.error ?? undefined}>
          Scan failed: {status.error}
        </p>
      )}
      {status?.state === "completed" && (
        <p className="text-[11px] leading-tight text-muted-foreground">
          {status.added} added · {status.updated} updated · {status.moved} moved
          {status.missing > 0 && ` · ${status.missing} missing`}
          {status.error_count > 0 && <span className="text-destructive"> · {status.error_count} errors</span>}
        </p>
      )}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="row-span-1 flex min-h-0 flex-col gap-5 border-r border-border px-3 py-4">
      <Link href="/library" className="px-2 text-sm font-bold tracking-[0.2em]">
        CUE<span className="text-primary">FLOW</span>
      </Link>

      <section className="flex flex-col gap-1.5">
        <h2 className="px-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Library</h2>
        <Suspense>
          <Views />
        </Suspense>
      </section>

      <section className="flex flex-col gap-1.5">
        <h2 className="px-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Tools</h2>
        <Tools />
      </section>

      <section className="flex min-h-0 flex-1 flex-col gap-1.5">
        <h2 className="px-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Folders</h2>
        <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          <Suspense>
            <FolderTree />
          </Suspense>
        </div>
      </section>

      <section className="flex flex-col gap-1.5">
        <h2 className="px-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Playlists</h2>
        <p className="flex items-center gap-2 px-2 text-xs text-muted-foreground/60">
          <ListMusic className="size-4" /> Coming in 0.4
        </p>
      </section>

      <div className="flex flex-col gap-2">
        <JobControl
          id="audio"
          compact
          status={api.audioStatus}
          start={() => api.startAudio()}
          stop={api.stopAudio}
          invalidate={AUDIO_JOB_REFRESH}
          label="Analyse audio"
          icon={<AudioLines />}
          hint="BPM, beatgrid, bar 1, key and energy for every track (≈5 s per track, 3 in parallel)"
        />
        <ScanButton />
      </div>
    </aside>
  );
}
