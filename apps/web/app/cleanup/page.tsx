"use client";

import { useState } from "react";

import { Duplicates } from "@/components/cleanup/Duplicates";
import { ShortTracks } from "@/components/cleanup/ShortTracks";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "duplicates", label: "Duplicates" },
  { id: "short", label: "Short tracks" },
] as const;

export default function CleanupPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("duplicates");
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-1 border-b border-border px-4 py-3">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn("rounded-md px-2.5 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-foreground", tab === t.id && "bg-muted text-foreground")}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-muted-foreground">Removed files go to the macOS Trash — nothing is deleted permanently.</span>
      </header>
      {tab === "duplicates" ? <Duplicates /> : <ShortTracks />}
    </div>
  );
}
