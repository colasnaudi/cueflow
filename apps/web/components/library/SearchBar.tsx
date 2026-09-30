"use client";

import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";

export function SearchBar({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [committed, setCommitted] = useState(value);
  const input = useRef<HTMLInputElement>(null);

  // Follow external changes (sidebar navigation, back button).
  if (value !== committed) {
    setCommitted(value);
    setDraft(value);
  }

  useEffect(() => {
    if (draft === value) return;
    const timer = setTimeout(() => onChange(draft), 250);
    return () => clearTimeout(timer);
  }, [draft, value, onChange]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        ref={input}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && setDraft("")}
        placeholder="Search artist, title, album, label…"
        className="pl-8"
        aria-label="Search library"
      />
      <kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-[10px] text-muted-foreground">
        ⌘K
      </kbd>
    </div>
  );
}
