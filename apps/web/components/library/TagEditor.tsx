"use client";

import type { Tag, TagCount } from "@cueflow/types";
import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Input } from "@/components/ui/input";

interface TagEditorProps {
  tags: Tag[];
  suggestions: TagCount[] | undefined;
  onAdd: (name: string) => void;
  onRemove: (tagId: string) => void;
  pending?: boolean;
}

export function TagEditor({ tags, suggestions, onAdd, onRemove, pending }: TagEditorProps) {
  const [draft, setDraft] = useState("");
  const present = new Set(tags.map((t) => t.name));
  const submit = () => {
    const name = draft.trim().replace(/^#/, "");
    if (name) onAdd(name);
    setDraft("");
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((tag) => (
        <span key={tag.id} className="inline-flex items-center gap-1 rounded-md bg-muted py-0.5 pr-1 pl-2 text-xs">
          #{tag.name}
          <button type="button" onClick={() => onRemove(tag.id)} aria-label={`Remove tag ${tag.name}`} className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground">
            <X className="size-3" />
          </button>
        </span>
      ))}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        className="relative"
      >
        <Plus className="pointer-events-none absolute top-1/2 left-2 size-3 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          list="tag-suggestions"
          placeholder="Add tag"
          disabled={pending}
          className="h-6 w-32 pl-6 text-xs"
          aria-label="Add tag"
        />
        <datalist id="tag-suggestions">
          {suggestions?.filter((s) => !present.has(s.name)).map((s) => <option key={s.id} value={s.name} />)}
        </datalist>
      </form>
    </div>
  );
}
