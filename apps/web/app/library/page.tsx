"use client";

import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Suspense, useCallback } from "react";

import { FilterBar } from "@/components/library/FilterBar";
import { FolderBreadcrumb } from "@/components/library/FolderBreadcrumb";
import { SearchBar } from "@/components/library/SearchBar";
import { TrackTable } from "@/components/library/TrackTable";
import { api } from "@/lib/api";
import { useLibraryQuery } from "@/lib/library-query";

const PAGE_SIZE = 100;

function Library() {
  const { query, params, update } = useLibraryQuery();

  const tracks = useInfiniteQuery({
    queryKey: ["tracks", query],
    queryFn: ({ pageParam }) => api.tracks(query, pageParam, PAGE_SIZE),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined),
    placeholderData: keepPreviousData,
  });
  const facets = useQuery({ queryKey: ["facets", query.min_duration_ms], queryFn: () => api.facets(query.min_duration_ms) });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });

  const items = tracks.data?.pages.flatMap((page) => page.items) ?? [];
  const total = tracks.data?.pages[0]?.total;
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = tracks;
  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const onSearch = useCallback((q: string) => update({ q }), [update]);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-border px-4 py-3">
        <SearchBar value={query.q ?? ""} onChange={onSearch} />
        {query.folder && <FolderBreadcrumb folder={query.folder} update={update} />}
        <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
          {total !== undefined ? `${total.toLocaleString()} tracks` : ""}
        </span>
      </header>

      <FilterBar
        query={query}
        facets={facets.data}
        tags={tags.data}
        showSamples={params.get("samples") === "1"}
        showDuplicates={params.get("duplicates") === "1"}
        update={update}
      />

      {tracks.isError ? (
        <p className="p-8 text-sm text-destructive">
          Cannot reach the API ({tracks.error.message}). Is it running on port 8000? Try <code>pnpm dev</code>.
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <TrackTable
            tracks={items}
            query={query}
            onSort={(sort, order) => update({ sort, order: order === "desc" ? "desc" : undefined })}
            hasMore={!!hasNextPage}
            loadMore={loadMore}
            loading={tracks.isLoading || isFetchingNextPage}
          />
        </div>
      )}
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense>
      <Library />
    </Suspense>
  );
}
