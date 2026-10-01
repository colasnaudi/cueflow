"""Deterministic DSP analysis: BPM, constant beatgrid, downbeat, key and per-bar energy (Essentia).

House / tech house is produced at a constant tempo, so like DJ software we fit ONE constant grid
(tempo + phase) to the whole track instead of trusting every beat tick: a beat tracker drifts or flips
phase in breakdowns, a constant grid does not.
"""

import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.audio.structure import detect_sections, downbeat_shift
from app.audio.vocals import per_bar, vocal_model

ANALYZER_VERSION = "cueflow-dsp-v4"  # v4: drops placed to the beat, no phrase snapping
BEAT_MODEL = "final0"
SAMPLE_RATE = 44100
BEATS_PER_BAR = 4
KEY_PROFILE = (
    "bgate"  # best exact-match rate on a 40-track house benchmark (edma, temperley, shaath were worse)
)
# A grid is trusted when most beat ticks sit on it (circular concentration, 1 = perfect).
MIN_TRUSTED_ALIGNMENT = 0.8
SNAP_TOLERANCE_BPM = 0.03
ENERGY_RANGE_DB = 30
# Bar 1 moved so that drops start bars: kick + bass coming back is a far clearer downbeat cue than the model.
DROP_ALIGNED_CONFIDENCE = 0.9


@dataclass
class RhythmAnalysis:
    bpm: float
    first_beat: float  # seconds; beat k is at first_beat + k * 60 / bpm
    downbeat_offset: int  # index (0-3) of the first beat that starts a bar
    beat_count: int
    grid_confidence: float  # 0-1: how well the audio's beats sit on the constant grid
    downbeat_confidence: float  # 0-1: share of the model's downbeats agreeing with the chosen bar phase
    musical_key: str | None
    camelot_key: str | None
    key_strength: float
    energy_curve: list[float]  # one value per bar, 0-1 relative to the track's loudest bar
    sections: list[dict]  # [{"type": "BREAK", "start_bar": 48, "end_bar": 72, "confidence": 0.8}]
    vocal_curve: list[float]  # voice probability per bar
    vocal_probability: float  # share of the track with a voice
    duration: float

    def as_dict(self) -> dict:
        return asdict(self)


def alignment(times: np.ndarray, weights: np.ndarray, period: float) -> float:
    """Circular concentration of `times` folded on `period` (Rayleigh R, weighted)."""
    phase = np.exp(2j * np.pi * (times % period) / period)
    return float(np.abs(np.sum(weights * phase)) / np.sum(weights))


def grid_phase(times: np.ndarray, weights: np.ndarray, period: float) -> float:
    angle = np.angle(np.sum(weights * np.exp(2j * np.pi * (times % period) / period)))
    return float((angle / (2 * np.pi) * period) % period)


def best_tempo(times: np.ndarray, weights: np.ndarray, guess: float, span: float = 2.0) -> float:
    """Coarse (0.01 BPM) then fine (0.001 BPM) search of the tempo that best folds `times`."""
    bpms = np.arange(guess - span, guess + span, 0.01)
    best = bpms[int(np.argmax([alignment(times, weights, 60 / b) for b in bpms]))]
    fine = np.arange(best - 0.02, best + 0.02, 0.001)
    return float(fine[int(np.argmax([alignment(times, weights, 60 / b) for b in fine]))])


def onset_envelope(audio: np.ndarray, hop: int = 256) -> tuple[np.ndarray, np.ndarray]:
    import essentia.standard as es

    window, fft, polar = es.Windowing(type="hann"), es.FFT(), es.CartesianToPolar()
    flux = es.OnsetDetection(method="flux")
    frames = es.FrameGenerator(audio, frameSize=1024, hopSize=hop, startFromZero=True)
    env = np.asarray([flux(*polar(fft(window(f)))) for f in frames])
    # Timestamp each value at its frame centre, where a windowed attack peaks.
    times = (np.arange(len(env)) * hop + 512) / SAMPLE_RATE
    return times, np.maximum(env - np.median(env), 0) + 1e-9


def refine_phase(onsets: tuple[np.ndarray, np.ndarray], bpm: float, first_beat: float) -> float:
    """Beat-tracker ticks land ~20 ms early: slide the grid (±40 ms) onto the onset envelope attacks."""
    times, env = onsets
    period = 60 / bpm
    grid = np.arange(first_beat % period, times[-1], period)
    shifts = np.arange(-0.04, 0.0405, 0.001)
    scores = [np.interp(grid + shift, times, env).sum() for shift in shifts]
    return float((first_beat + shifts[int(np.argmax(scores))]) % period)


def fit_grid(audio: np.ndarray) -> tuple[float, float, float]:
    """(bpm, first_beat, confidence) of the constant grid that best explains the track."""
    import essentia.standard as es

    guess, ticks, *_ = es.RhythmExtractor2013(method="multifeature")(audio)
    ticks = np.asarray(ticks, dtype=float)
    if len(ticks) < 16:
        raise ValueError("not enough beats detected")
    ones = np.ones_like(ticks)

    first = best_tempo(ticks, ones, guess)
    candidates = {first}
    onsets = onset_envelope(audio)
    messy = alignment(ticks, ones, 60 / first) < MIN_TRUSTED_ALIGNMENT
    if messy:
        # Messy ticks (breakdowns, swing): let the raw onset envelope vote too.
        candidates.add(best_tempo(*onsets, guess))
    candidates |= {float(round(c)) for c in candidates}

    def score(bpm: float) -> float:
        value = alignment(ticks, ones, 60 / bpm)
        return value + (alignment(*onsets, 60 / bpm) if messy else 0)

    bpm = max(candidates, key=score)
    # Productions are made at integer tempos: snap when it costs (almost) nothing.
    rounded = float(round(bpm))
    if abs(bpm - rounded) <= SNAP_TOLERANCE_BPM and score(rounded) >= 0.98 * score(bpm):
        bpm = rounded
    period = 60 / bpm
    first_beat = refine_phase(onsets, bpm, grid_phase(ticks, ones, period))
    return bpm, first_beat, alignment(ticks, ones, period)


class DownbeatModel:
    """beat_this (CPJKU, 2024) neural beat/downbeat tracker, loaded once per process.

    Benchmark, 60 house tracks: bar starts right in 41/60 (a timbre-novelty heuristic: 17/60, i.e. chance).
    Only its downbeats are used: the BPM and beat positions come from the constant grid.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None

    def downbeats(self, audio: np.ndarray) -> np.ndarray:
        with self._lock:
            if self._model is None:
                from beat_this.inference import Audio2Beats

                self._model = Audio2Beats(checkpoint_path=str(ensure_beat_model()), device="cpu", dbn=False)
            _, downbeats = self._model(audio, SAMPLE_RATE)
        return np.asarray(downbeats, dtype=float)


downbeat_model = DownbeatModel()


def ensure_beat_model() -> Path:
    from beat_this.inference import CHECKPOINT_URL

    from app.audio.styles import download, models_dir

    target = models_dir() / f"beat_this-{BEAT_MODEL}.ckpt"
    if not target.exists():
        download(f"{CHECKPOINT_URL}/{BEAT_MODEL}.ckpt", target)
    return target


def downbeat_phase(downbeats: np.ndarray, first_beat: float, period: float) -> tuple[int, float]:
    """Bar phase (0-3) on the constant grid: majority vote of the model's downbeats (confidence = share)."""
    if len(downbeats) == 0:
        return 0, 0.0
    beat_index = np.round((downbeats - first_beat) / period).astype(int)
    votes = np.bincount(beat_index % BEATS_PER_BAR, minlength=BEATS_PER_BAR)
    phase = int(np.argmax(votes))
    return phase, round(float(votes[phase] / votes.sum()), 3)


def bar_energy(audio: np.ndarray, bar_starts: np.ndarray) -> list[float]:
    """RMS per bar in dB, rescaled to 0-1 over the ENERGY_RANGE_DB below the loudest bar.

    Mastered house sits within a few dB from intro to drop: a 30 dB range keeps breaks visible.
    """
    values = []
    for start, end in zip(bar_starts[:-1], bar_starts[1:], strict=True):
        segment = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
        rms = np.sqrt(np.mean(np.square(segment))) if len(segment) else 0.0
        values.append(20 * np.log10(rms + 1e-9))
    if not values:
        return []
    db = np.asarray(values, dtype=np.float64)  # float32 audio would store 0.2319999933 in JSON
    return np.round(np.clip((db - (db.max() - ENERGY_RANGE_DB)) / ENERGY_RANGE_DB, 0, 1), 3).tolist()


def band_frames(audio: np.ndarray) -> tuple[np.ndarray, ...]:
    """Frame times and power of the low (< 120 Hz), mid (150 Hz - 2 kHz) and high (> 4 kHz) bands.

    Short frames (46 ms, 23 ms hop) separate a kick from the gap after it, so a kick alone and kick + bassline
    look different.
    """
    import essentia.standard as es

    frame, hop = 2048, 1024
    window, spectrum = es.Windowing(type="hann"), es.Spectrum()
    frames = es.FrameGenerator(audio, frameSize=frame, hopSize=hop, startFromZero=True)
    power = np.array([spectrum(window(f)) for f in frames], dtype=np.float64) ** 2
    times = (np.arange(len(power)) * hop + frame / 2) / SAMPLE_RATE
    freqs = np.fft.rfftfreq(frame, 1 / SAMPLE_RATE)
    low = power[:, freqs < 120].sum(axis=1)
    mid = power[:, (freqs >= 150) & (freqs < 2000)].sum(axis=1)
    high = power[:, freqs >= 4000].sum(axis=1)
    return times, low, mid, high


def segment_features(bands: tuple[np.ndarray, ...], boundaries: np.ndarray) -> np.ndarray:
    """Per segment (bar or beat), in dB: kick (95th percentile of the low band: the hits), bass (its 30th
    percentile: what remains between the hits), mid and high (means) — the structure engine's input."""
    times, low, mid, high = bands
    rows = []
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        inside = (times >= start) & (times < end)
        if not inside.any():  # segment shorter than a frame: nearest frame
            inside = np.zeros(len(times), dtype=bool)
            inside[int(np.argmin(np.abs(times - start)))] = True
        values = (
            np.percentile(low[inside], 95),
            np.percentile(low[inside], 30),
            mid[inside].mean(),
            high[inside].mean(),
        )
        rows.append([10 * np.log10(v + 1e-12) for v in values])
    return np.asarray(rows, dtype=np.float64).reshape(-1, 4)


def bar_features(audio: np.ndarray, bar_starts: np.ndarray) -> np.ndarray:
    return segment_features(band_frames(audio), bar_starts)


def detect_key(audio: np.ndarray) -> tuple[str | None, str | None, float]:
    import essentia.standard as es

    from app.audio.keys import normalize_key

    key, scale, strength = es.KeyExtractor(profileType=KEY_PROFILE)(audio)
    musical, camelot = normalize_key(f"{key}{'m' if scale == 'minor' else ''}")
    return musical, camelot, round(float(strength), 3)


def analyse(path: str) -> RhythmAnalysis:
    import essentia
    import essentia.standard as es

    essentia.log.warningActive = False
    audio = es.MonoLoader(filename=str(path), sampleRate=SAMPLE_RATE)()
    duration = len(audio) / SAMPLE_RATE

    bpm, first_beat, grid_confidence = fit_grid(audio)
    beats = np.arange(first_beat, duration, 60 / bpm)
    phase, downbeat_confidence = downbeat_phase(downbeat_model.downbeats(audio), first_beat, 60 / bpm)
    musical, camelot, strength = detect_key(audio)
    bands = band_frames(audio)
    beat_features = segment_features(bands, np.append(beats, duration))

    def structure(phase: int) -> tuple[np.ndarray, list]:
        bar_starts = np.append(beats[phase::BEATS_PER_BAR], duration)
        bar_features = segment_features(bands, bar_starts)
        return bar_starts, detect_sections(bar_features, beat_features=beat_features, first_bar_beat=phase)

    bar_starts, sections = structure(phase)
    # Drops land on bar 1 of a bar: when they agree on another beat, the downbeat model was wrong.
    shift = downbeat_shift(sections)
    if shift:
        phase = (phase + shift) % BEATS_PER_BAR
        downbeat_confidence = max(downbeat_confidence, DROP_ALIGNED_CONFIDENCE)
        bar_starts, sections = structure(phase)
    voice = vocal_model.voice_timeline(path)

    return RhythmAnalysis(
        bpm=round(bpm, 3),
        first_beat=round(first_beat, 4),
        downbeat_offset=phase,
        beat_count=len(beats),
        grid_confidence=round(grid_confidence, 3),
        downbeat_confidence=downbeat_confidence,
        musical_key=musical,
        camelot_key=camelot,
        key_strength=strength,
        energy_curve=bar_energy(audio, bar_starts),
        sections=[section.as_dict() for section in sections],
        vocal_curve=per_bar(voice, bar_starts),
        vocal_probability=round(float(voice.mean()), 3) if len(voice) else 0.0,
        duration=round(duration, 3),
    )
