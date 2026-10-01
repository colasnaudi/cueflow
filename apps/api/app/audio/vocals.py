"""Vocal activity: Essentia voice/instrumental head on Discogs-EffNet embeddings (one value per ~1 s)."""

import json
import threading

import numpy as np

from app.audio.styles import EMBEDDING_MODEL, download, ensure_models, models_dir

MODEL = "voice_instrumental-discogs-effnet-1"
MODEL_URL = "https://essentia.upf.edu/models/classification-heads/voice_instrumental"
EMBEDDING_RATE = 16000
PATCH_SECONDS = 1.0  # TensorflowPredictEffnetDiscogs hops ~1 s between patches


class VocalModel:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models = None

    def _load(self):
        import essentia.standard as es

        ensure_models()
        for suffix in (".pb", ".json"):
            target = models_dir() / f"{MODEL}{suffix}"
            if not target.exists():
                download(f"{MODEL_URL}/{MODEL}{suffix}", target)
        classes = json.loads((models_dir() / f"{MODEL}.json").read_text())["classes"]
        embedding = es.TensorflowPredictEffnetDiscogs(
            graphFilename=str(models_dir() / EMBEDDING_MODEL), output="PartitionedCall:1"
        )
        head = es.TensorflowPredict2D(graphFilename=str(models_dir() / f"{MODEL}.pb"), output="model/Softmax")
        return classes.index("voice"), embedding, head

    def voice_timeline(self, path: str) -> np.ndarray:
        """Probability of a voice for each ~1 s of the track."""
        import essentia.standard as es

        with self._lock:
            if self._models is None:
                self._models = self._load()
            voice, embedding, head = self._models
            audio = es.MonoLoader(filename=str(path), sampleRate=EMBEDDING_RATE, resampleQuality=4)()
            return np.asarray(head(embedding(audio))[:, voice], dtype=np.float64)


vocal_model = VocalModel()


def per_bar(timeline: np.ndarray, bar_starts: np.ndarray) -> list[float]:
    """Mean voice probability of the ~1 s patches inside each bar (nearest patch for very short bars)."""
    if len(timeline) == 0:
        return []
    times = (np.arange(len(timeline)) + 0.5) * PATCH_SECONDS
    values = []
    for start, end in zip(bar_starts[:-1], bar_starts[1:], strict=True):
        inside = (times >= start) & (times < end)
        value = timeline[inside].mean() if inside.any() else timeline[min(len(timeline) - 1, int(start))]
        values.append(round(float(value), 3))
    return values
