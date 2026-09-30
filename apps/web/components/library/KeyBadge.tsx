import { camelotColor } from "@/lib/format";
import { cn } from "@/lib/utils";

export function KeyBadge({ camelot, className }: { camelot: string | null | undefined; className?: string }) {
  if (!camelot) return <span className={cn("text-muted-foreground", className)}>–</span>;
  return (
    <span
      className={cn("inline-flex min-w-9 justify-center rounded px-1.5 py-0.5 font-mono text-xs font-semibold text-black", className)}
      style={{ backgroundColor: camelotColor(camelot) }}
    >
      {camelot}
    </span>
  );
}
