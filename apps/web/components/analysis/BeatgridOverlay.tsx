import type { Cue, TrackAnalysis } from "@cueflow/types";

import { SECTION_STYLE, barStarts, barTime, positionLabel, positionTime } from "@/lib/beatgrid";

const PHRASE_BARS = 8;

/** Sections, bar lines (phrase every 8 bars, numbered), vocal and energy strips, aligned on the waveform. */
export function BeatgridOverlay({ analysis, cues = [], duration }: { analysis: TrackAnalysis; cues?: Cue[]; duration: number }) {
  if (!analysis.beatgrid || duration <= 0) return null;
  const starts = barStarts(analysis.beatgrid, duration);
  const pct = (t: number) => `${(t / duration) * 100}%`;

  const strip = (curve: number[], bottom: string, color: string, label: string) =>
    curve.map((value, bar) =>
      starts[bar] === undefined ? null : (
        <div
          key={`${label}${bar}`}
          className={`absolute h-1 ${bottom} ${color}`}
          style={{
            left: pct(starts[bar]),
            width: pct(barTime(starts, bar + 1, duration) - starts[bar]),
            opacity: 0.08 + 0.92 * value ** 2,
          }}
          title={`Bar ${bar + 1} · ${label} ${Math.round(value * 100)}%`}
        />
      ),
    );

  return (
    <>
      {analysis.sections.map((section) => {
        const grid = analysis.beatgrid!;
        const start = positionTime(grid, starts, section.start_bar, section.start_beat, duration);
        const end = positionTime(grid, starts, section.end_bar, section.end_beat, duration);
        const style = SECTION_STYLE[section.type];
        return (
          <div
            key={`${section.type}${section.start_bar}.${section.start_beat}`}
            className={`absolute top-0 flex h-4 items-center overflow-hidden border-l border-background/60 px-1 text-[9px] font-semibold tracking-wider uppercase ${style.className}`}
            style={{ left: pct(start), width: pct(end - start) }}
            title={`${style.label} · from bar ${positionLabel(section.start_bar, section.start_beat)}`}
          >
            {style.label}
          </div>
        );
      })}
      {starts.map((start, bar) => {
        const phrase = bar % PHRASE_BARS === 0;
        return (
          <div key={bar} className="absolute top-4 bottom-3" style={{ left: pct(start) }}>
            <div className={phrase ? "h-full w-px bg-primary/70" : "h-full w-px bg-foreground/10"} />
            {phrase && <span className="absolute top-0 left-1 font-mono text-[9px] leading-none text-primary">{bar + 1}</span>}
          </div>
        );
      })}
      {cues
        .filter((cue) => cue.type === "HOT")
        .map((cue) => (
          <div
            key={cue.id}
            className="absolute top-4 bottom-3 w-px"
            style={{ left: pct(positionTime(analysis.beatgrid!, starts, cue.bar, cue.beat, duration)), backgroundColor: cue.color ?? "#888" }}
            title={`${cue.slot} · ${cue.label}`}
          >
            <span className="absolute bottom-0 left-0 rounded-r px-1 font-mono text-[9px] leading-3 font-bold text-black" style={{ backgroundColor: cue.color ?? "#888" }}>
              {cue.slot}
            </span>
          </div>
        ))}
      {strip(analysis.vocal_curve, "bottom-1.5", "bg-cyan-400", "voice")}
      {strip(analysis.energy_curve, "bottom-0", "bg-primary", "energy")}
    </>
  );
}
