"use client";

import type { FolderNode } from "@cueflow/types";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { api } from "@/lib/api";

function flatten(nodes: FolderNode[], depth = 0): { path: string; label: string; count: number }[] {
  return nodes.flatMap((node) => [
    { path: node.path, label: `${"  ".repeat(depth)}${node.name.replaceAll(":", "/")}`, count: node.count },
    ...flatten(node.children, depth + 1),
  ]);
}

function Option({ checked, onChange, title, children }: { checked: boolean; onChange: (v: boolean) => void; title: string; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-md border border-border p-3 hover:bg-muted/40">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 accent-[var(--primary)]" />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-muted-foreground">{children}</span>
      </span>
    </label>
  );
}

export default function ExportPage() {
  const [folder, setFolder] = useState("");
  const [approvedOnly, setApprovedOnly] = useState(true);
  const [includeBeatgrid, setIncludeBeatgrid] = useState(true);
  const folders = useQuery({ queryKey: ["folders", "export"], queryFn: () => api.folders(60_000, false) });
  const preview = useQuery({
    queryKey: ["export-preview", folder, approvedOnly],
    queryFn: () => api.exportPreview(folder || undefined, approvedOnly),
  });
  const download = useMutation({
    mutationFn: () => api.exportRekordbox({ folder: folder || undefined, approved_only: approvedOnly, include_beatgrid: includeBeatgrid }),
  });
  const ready = (preview.data?.tracks ?? 0) > 0;

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-8 py-8">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Rekordbox export</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Builds a <code>rekordbox.xml</code> with your hot cues, memory cues and beatgrids. Cueflow never touches the
            Rekordbox database: you import the file yourself.
          </p>
        </header>

        <section className="flex flex-col gap-2">
          <label htmlFor="folder" className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
            Tracks of
          </label>
          <select
            id="folder"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            className="h-9 rounded-md border border-border bg-background px-2 text-sm"
          >
            <option value="">The whole library</option>
            {folders.data && flatten(folders.data).map((f) => <option key={f.path} value={f.path}>{f.label} ({f.count})</option>)}
          </select>
          <p className="text-xs text-muted-foreground">
            Rekordbox <strong>adds</strong> the XML tracks it does not know yet: pick the folder you play from, not a
            whole library full of copies.
          </p>
        </section>

        <section className="flex flex-col gap-2">
          <Option checked={approvedOnly} onChange={setApprovedOnly} title="Only approved cues">
            Tracks whose cues you approved on their page. Untick to export the suggestions as they are.
          </Option>
          <Option checked={includeBeatgrid} onChange={setIncludeBeatgrid} title="Include the beatgrid">
            Replaces the track&apos;s grid in Rekordbox with Cueflow&apos;s (BPM + bar 1), so quantized cues and the grid agree.
            Untick to keep your Rekordbox grids.
          </Option>
        </section>

        <section className="flex items-center gap-4 rounded-lg border border-border bg-card px-4 py-3">
          <div className="text-sm">
            {preview.data ? (
              <>
                <span className="font-mono tabular-nums">{preview.data.tracks}</span> tracks ·{" "}
                <span className="font-mono tabular-nums">{preview.data.hot_cues}</span> hot cues ·{" "}
                <span className="font-mono tabular-nums">{preview.data.memory_cues}</span> memory cues
                {approvedOnly && preview.data.unapproved_tracks > 0 && (
                  <p className="text-xs text-amber-300">{preview.data.unapproved_tracks} analysed tracks have cues waiting for approval.</p>
                )}
              </>
            ) : (
              "…"
            )}
          </div>
          <Button className="ml-auto" onClick={() => download.mutate()} disabled={!ready || download.isPending}>
            <Download /> Download rekordbox.xml
          </Button>
        </section>
        <ErrorNotice error={preview.error ?? download.error} action="Export" className="rounded border" />
        {download.data && <p className="text-xs text-primary">Saved {download.data} (a copy is kept in data/exports/).</p>}

        <section className="flex flex-col gap-3 text-sm">
          <h2 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Import in Rekordbox</h2>
          <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
            <TriangleAlert className="mt-px size-4 shrink-0" />
            Importing overwrites the hot cues, memory cues and (if included) beatgrids of these tracks in Rekordbox.
            Back up first: File → Library → Backup Library. Try one playlist before a whole folder.
          </p>
          <ol className="list-decimal space-y-1.5 pl-5 text-muted-foreground">
            <li>Preferences → Advanced → Database → rekordbox xml: choose the downloaded file.</li>
            <li>Preferences → View → Layout: tick “rekordbox xml” to show it in the tree.</li>
            <li>In the tree, open rekordbox xml → Playlists → the Cueflow playlist.</li>
            <li>
              Select the <strong>tracks</strong> (Cmd/Ctrl+A), right click → <strong>Import To Collection</strong>. Importing only
              the playlist does not update tracks already in your collection.
            </li>
            <li>Check one MP3 and one WAV: hot cues should sit exactly on the kick.</li>
          </ol>
        </section>
      </div>
    </div>
  );
}
