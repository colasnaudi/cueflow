"use client";

import { Folder, X } from "lucide-react";

type Update = (changes: Record<string, string | undefined>) => void;

export function FolderBreadcrumb({ folder, update }: { folder: string; update: Update }) {
  const parts = folder.split("/");
  return (
    <nav aria-label="Folder" className="flex min-w-0 items-center gap-1 text-xs">
      <Folder className="size-3.5 shrink-0 text-primary" />
      {parts.map((part, index) => {
        const path = parts.slice(0, index + 1).join("/");
        const last = index === parts.length - 1;
        return (
          <span key={path} className="flex min-w-0 items-center gap-1">
            <button
              type="button"
              onClick={() => update({ folder: path })}
              className={last ? "truncate font-medium text-foreground" : "truncate text-muted-foreground hover:text-foreground"}
            >
              {part.replaceAll(":", "/")}
            </button>
            {!last && <span className="text-muted-foreground/50">/</span>}
          </span>
        );
      })}
      <button type="button" onClick={() => update({ folder: undefined })} aria-label="Show all folders" className="ml-1 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">
        <X className="size-3" />
      </button>
    </nav>
  );
}
