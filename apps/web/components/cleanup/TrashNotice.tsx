import type { TrashResult } from "@cueflow/types";

import { formatBytes } from "@/lib/format";

export function TrashNotice({ result }: { result: TrashResult | undefined }) {
  if (!result) return null;
  return (
    <div className="border-b border-border bg-primary/10 px-4 py-2 text-xs">
      {result.removed} file{result.removed === 1 ? "" : "s"} moved to the Trash ({formatBytes(result.freed_bytes)} freed). Restore them from
      the Finder Trash with &ldquo;Put Back&rdquo;, then rescan.
      {result.errors.length > 0 && (
        <details className="mt-1 text-destructive">
          <summary>{result.errors.length} errors</summary>
          <ul className="mt-1 font-mono">{result.errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </details>
      )}
    </div>
  );
}
