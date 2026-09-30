"use client";

import { Star } from "lucide-react";

import { cn } from "@/lib/utils";

interface RatingProps {
  value: number;
  onChange?: (value: number) => void;
  size?: "sm" | "md";
}

export function Rating({ value, onChange, size = "sm" }: RatingProps) {
  const icon = size === "sm" ? "size-3" : "size-4";
  return (
    <div className="flex items-center" role={onChange ? "radiogroup" : undefined} aria-label={`Rating ${value} of 5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={!onChange}
          aria-label={`${star} star${star > 1 ? "s" : ""}`}
          // Clicking the current rating clears it.
          onClick={(event) => {
            event.stopPropagation();
            onChange?.(star === value ? 0 : star);
          }}
          className={cn("p-px enabled:cursor-pointer enabled:hover:scale-110", star <= value ? "text-amber-400" : "text-muted-foreground/30")}
        >
          <Star className={cn(icon, star <= value && "fill-current")} />
        </button>
      ))}
    </div>
  );
}
