"use client";

import type { SortField, TrackQuery } from "@cueflow/types";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

export const SAMPLE_THRESHOLD_MS = 60_000;

const numberOrUndefined = (value: string | null) => (value === null || value === "" ? undefined : Number(value));

/** Library filters live in the URL so views are shareable and survive reloads / back navigation. */
export function useLibraryQuery() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const query = useMemo<TrackQuery>(
    () => ({
      q: params.get("q") ?? undefined,
      genre: params.getAll("genre"),
      key: params.getAll("key"),
      tag: params.getAll("tag"),
      bpm_min: numberOrUndefined(params.get("bpm_min")),
      bpm_max: numberOrUndefined(params.get("bpm_max")),
      rating_min: numberOrUndefined(params.get("rating_min")),
      min_duration_ms: params.get("samples") === "1" ? undefined : SAMPLE_THRESHOLD_MS,
      dedupe: params.get("duplicates") !== "1",
      folder: params.get("folder") ?? undefined,
      sort: (params.get("sort") as SortField | null) ?? "artist",
      order: params.get("order") === "desc" ? "desc" : "asc",
    }),
    [params],
  );

  /** Merge `changes` into the URL; `undefined`, empty string and empty arrays remove the parameter. */
  const update = useCallback(
    (changes: Record<string, string | string[] | number | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(changes)) {
        next.delete(key);
        for (const item of Array.isArray(value) ? value : [value]) {
          if (item !== undefined && item !== "") next.append(key, String(item));
        }
      }
      const search = next.toString();
      router.replace(search ? `${pathname}?${search}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { query, params, update };
}
