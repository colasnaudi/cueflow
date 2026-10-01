"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AudioLines, Download, FolderOpen, FolderSync, ListMusic, RotateCcw, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuGroup,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { api } from "@/lib/api";

interface FolderMenuProps {
  path: string;
  name: string;
  count: number;
  children: React.ReactNode;
}

/** Right-click actions on a library folder (always the folder and everything below it). */
export function FolderMenu({ path, name, count, children }: FolderMenuProps) {
  const client = useQueryClient();
  const router = useRouter();
  const label = name.replaceAll(":", "/");

  const run = (action: () => Promise<unknown>, done: string, refresh: string[][] = []) =>
    action()
      .then(() => {
        toast.success(done);
        for (const key of refresh) void client.invalidateQueries({ queryKey: key });
      })
      .catch((error: Error) =>
        toast.error(error.message.includes("already running") ? "An analysis is already running — wait or stop it." : error.message),
      );

  return (
    <ContextMenu>
      <ContextMenuTrigger render={<div />}>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-72">
        <ContextMenuGroup>
          {/* Base UI: a label must live inside a group */}
          <ContextMenuLabel className="truncate">
            {label} <span className="font-normal text-muted-foreground">· {count} tracks</span>
          </ContextMenuLabel>
          <ContextMenuItem onClick={() => router.push(`/library?folder=${encodeURIComponent(path)}`)}>
            <ListMusic /> Show tracks
          </ContextMenuItem>
        </ContextMenuGroup>
        <ContextMenuSeparator />
        <ContextMenuItem
          onClick={() =>
            run(() => api.startAudio({ folder: path }), `Analysing ${label}: BPM, structure and cues. Progress in the sidebar.`, [["job", "audio"]])
          }
        >
          <AudioLines /> Analyse audio & cues
        </ContextMenuItem>
        <ContextMenuItem
          onClick={() =>
            run(
              () => api.startAudio({ folder: path, force: true }),
              `Re-analysing every track of ${label}. Cues you locked are kept.`,
              [["job", "audio"]],
            )
          }
        >
          <RotateCcw /> Re-analyse everything
        </ContextMenuItem>
        <ContextMenuItem
          onClick={() => run(() => api.startAnalysis(path), `Suggesting genres for ${label} — see Genre Review.`, [["job", "genres"]])}
        >
          <Sparkles /> Analyse genres
        </ContextMenuItem>
        <ContextMenuItem onClick={() => run(() => api.startScan(path), `Rescanning ${label}.`, [["scan"]])}>
          <FolderSync /> Rescan folder
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem
          onClick={() =>
            run(
              () => api.exportRekordbox({ folder: path, approved_only: true, include_beatgrid: true }),
              `Rekordbox XML of ${label} downloaded.`,
            )
          }
        >
          <Download /> Download Rekordbox XML
        </ContextMenuItem>
        <ContextMenuItem onClick={() => run(() => api.revealFolder(path), `Opened ${label} in the Finder.`)}>
          <FolderOpen /> Show in Finder
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}
