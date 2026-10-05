"use client";

/** A = the original, B = the working edit. */
export type EditorSide = "A" | "B";

export interface EngineState {
  playing: boolean;
  side: EditorSide;
  loop: boolean;
}

interface Bounds {
  start: number;
  end: number;
}

/**
 * Web Audio playback for the editor: two buffers (original and edited) through one output, so A/B switches
 * keep the same volume. The edit's gain is a live GainNode on B only, so the gain slider never re-renders.
 */
export class EditorEngine {
  readonly context: AudioContext;
  private buffers: Record<EditorSide, AudioBuffer>;
  private gain: GainNode;
  private node: AudioBufferSourceNode | null = null;
  /** Position (seconds) when paused, or where the running node started from. */
  private offset = 0;
  private startedAt = 0;
  /** Playback is limited to (and loops over, when `loop`) this range of the current side. */
  private bounds: Bounds | null = null;
  private gainDb = 0;
  private listeners = new Set<() => void>();
  state: EngineState = { playing: false, side: "B", loop: false };

  constructor(context: AudioContext, original: AudioBuffer, edited: AudioBuffer) {
    this.context = context;
    this.buffers = { A: original, B: edited };
    this.gain = new GainNode(context);
    this.gain.connect(context.destination);
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private setState(patch: Partial<EngineState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  get duration() {
    return this.buffers[this.state.side].duration;
  }

  /** Current position in seconds on the current side. */
  get position(): number {
    if (!this.state.playing) return this.offset;
    const elapsed = this.offset + this.context.currentTime - this.startedAt;
    const { bounds } = this;
    if (bounds && this.state.loop && elapsed >= bounds.end) {
      return bounds.start + ((elapsed - bounds.start) % (bounds.end - bounds.start));
    }
    return Math.min(elapsed, bounds?.end ?? this.duration);
  }

  setGainDb(db: number) {
    this.gainDb = db;
    this.gain.gain.value = this.state.side === "B" ? 10 ** (db / 20) : 1;
  }

  play(from = this.position, bounds: Bounds | null = null) {
    this.stopNode();
    const buffer = this.buffers[this.state.side];
    const start = Math.max(0, Math.min(from, buffer.duration));
    if (start >= (bounds?.end ?? buffer.duration)) return this.setState({ playing: false });
    void this.context.resume();
    const node = new AudioBufferSourceNode(this.context, { buffer });
    node.connect(this.gain);
    if (bounds && this.state.loop) {
      node.loop = true;
      node.loopStart = bounds.start;
      node.loopEnd = bounds.end;
      node.start(0, start);
    } else {
      node.start(0, start, (bounds?.end ?? buffer.duration) - start);
    }
    node.onended = () => {
      if (this.node !== node) return; // stopped or replaced on purpose
      this.offset = bounds?.end ?? buffer.duration;
      this.node = null;
      this.setState({ playing: false });
    };
    this.node = node;
    this.bounds = bounds;
    this.offset = start;
    this.startedAt = this.context.currentTime;
    this.setState({ playing: true });
  }

  pause() {
    this.offset = this.position;
    this.stopNode();
    this.setState({ playing: false });
  }

  seek(seconds: number) {
    const position = Math.max(0, Math.min(seconds, this.duration));
    if (this.state.playing) this.play(position, this.bounds && position < this.bounds.end ? this.bounds : null);
    else this.offset = position;
    this.listeners.forEach((listener) => listener());
  }

  setLoop(loop: boolean) {
    this.setState({ loop });
  }

  /** Switch A/B at `position` (seconds, already mapped onto the other side by the caller). */
  setSide(side: EditorSide, position: number) {
    const playing = this.state.playing;
    this.stopNode();
    this.state = { ...this.state, side };
    this.setGainDb(this.gainDb);
    this.offset = Math.max(0, Math.min(position, this.duration));
    if (playing) this.play(this.offset);
    else this.setState({});
  }

  /** A new render of the edit: B keeps playing from the same place (clamped to the new length). */
  setEdited(buffer: AudioBuffer) {
    const playing = this.state.playing && this.state.side === "B";
    const position = this.position;
    if (playing) this.stopNode();
    this.buffers.B = buffer;
    if (this.state.side === "B") this.offset = Math.min(position, buffer.duration);
    if (playing) this.play(this.offset);
  }

  private stopNode() {
    const node = this.node;
    this.node = null;
    this.bounds = null;
    node?.stop();
    node?.disconnect();
  }

  dispose() {
    this.stopNode();
    this.listeners.clear();
    void this.context.close();
  }
}
