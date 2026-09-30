"use client";

import type { FolderNode } from "@cueflow/types";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Folder, FolderOpen } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";
import { SAMPLE_THRESHOLD_MS } from "@/lib/library-query";
import { cn } from "@/lib/utils";

function folderHref(params: URLSearchParams, path: string) {
  const next = new URLSearchParams(params.toString());
  next.set("folder", path);
  return `/library?${next.toString()}`;
}

function Node({ node, depth, active, params }: { node: FolderNode; depth: number; active: string | null; params: URLSearchParams }) {
  const containsActive = !!active && (active === node.path || active.startsWith(`${node.path}/`));
  const [open, setOpen] = useState(containsActive && active !== node.path);
  const expanded = open || (containsActive && active !== node.path);
  const isActive = active === node.path;
  const Icon = expanded ? FolderOpen : Folder;

  return (
    <li>
      <div
        className={cn(
          "group flex items-center rounded-md pr-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground",
          isActive && "bg-muted text-foreground",
        )}
        style={{ paddingLeft: depth * 12 }}
      >
        <button
          type="button"
          onClick={() => setOpen(!expanded)}
          aria-label={expanded ? `Collapse ${node.name}` : `Expand ${node.name}`}
          className={cn("flex size-5 shrink-0 items-center justify-center", !node.children.length && "invisible")}
        >
          <ChevronRight className={cn("size-3 transition-transform", expanded && "rotate-90")} />
        </button>
        <Link href={folderHref(params, node.path)} className="flex min-w-0 flex-1 items-center gap-1.5 py-1" title={node.path}>
          <Icon className={cn("size-3.5 shrink-0", isActive && "text-primary")} />
          <span className="truncate">{node.name.replaceAll(":", "/")}</span>
          <span className="ml-auto pl-1 font-mono text-[10px] tabular-nums opacity-60">{node.count}</span>
        </Link>
      </div>
      {expanded && node.children.length > 0 && (
        <ul>
          {node.children.map((child) => (
            <Node key={child.path} node={child} depth={depth + 1} active={active} params={params} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function FolderTree() {
  const pathname = usePathname();
  const params = useSearchParams();
  // Same defaults as the library table, so counts match what a click shows.
  const minDuration = params.get("samples") === "1" ? undefined : SAMPLE_THRESHOLD_MS;
  const dedupe = params.get("duplicates") !== "1";
  const { data } = useQuery({ queryKey: ["folders", minDuration, dedupe], queryFn: () => api.folders(minDuration, dedupe) });
  const active = pathname === "/library" ? params.get("folder") : null;

  if (!data) return null;
  return (
    <ul className="flex flex-col">
      {data.map((node) => (
        <Node key={node.path} node={node} depth={0} active={active} params={pathname === "/library" ? params : new URLSearchParams()} />
      ))}
    </ul>
  );
}
