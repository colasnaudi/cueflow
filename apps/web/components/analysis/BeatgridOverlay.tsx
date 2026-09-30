import type { TrackAnalysis } from "@cueflow/types";

import { barStarts } from "@/lib/beatgrid";

const PHRASE_BARS = 8;

/** Bar lines (phrase every 8 bars, numbered) and a per-bar energy strip, aligned on the waveform. */
export function BeatgridOverlay({ analysis, duration }: { analysis: TrackAnalysis; duration: number }) {
  if (!analysis.beatgrid || duration <= 0) return null;
  const starts = barStarts(analysis.beatgrid, duration);
  const pct = (t: number) => `${(t / duration) * 100}%`;

  return (
    <>
      {starts.map((start, bar) => {
        const phrase = bar % PHRASE_BARS === 0;
        return (
          <div key={bar} className="absolute top-0 bottom-2" style={{ left: pct(start) }}>
            <div className={phrase ? "h-full w-px bg-primary/70" : "h-full w-px bg-foreground/10"} />
            {phrase && <span className="absolute top-0 left-1 font-mono text-[9px] leading-none text-primary">{bar + 1}</span>}
          </div>
        );
      })}
      {analysis.energy_curve.map((energy, bar) =>
        starts[bar] === undefined ? null : (
          <div
            key={`e${bar}`}
            className="absolute bottom-0 h-1.5 bg-primary"
            style={{
              left: pct(starts[bar]),
              width: pct((starts[bar + 1] ?? duration) - starts[bar]),
              opacity: 0.1 + 0.9 * energy ** 2,
            }}
            title={`Bar ${bar + 1} · energy ${Math.round(energy * 100)}%`}
          />
        ),
      )}
    </>
  );
}
