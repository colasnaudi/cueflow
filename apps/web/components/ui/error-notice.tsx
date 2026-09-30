import { TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";

/** Inline, actionable error: what failed and why. Renders nothing without an error. */
export function ErrorNotice({ error, action, className }: { error: unknown; action?: string; className?: string }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className={cn("flex items-start gap-2 border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-xs text-destructive", className)}>
      <TriangleAlert className="mt-px size-3.5 shrink-0" />
      <span>
        {action ? `${action} failed: ` : ""}
        {message}
        {message.includes("fetch") && " — is the API running on port 8000 (pnpm dev)?"}
      </span>
    </div>
  );
}
