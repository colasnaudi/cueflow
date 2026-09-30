"""Discogs-EffNet style classifier (Essentia). 400 Discogs styles, e.g. 'Electronic---Tech House'."""

import json
import threading
from functools import cached_property
from pathlib import Path

import numpy as np

from app.config import get_settings

ANALYZER_VERSION = "discogs-effnet-genre400-v1"
EMBEDDING_MODEL = "discogs-effnet-bs64-1.pb"
GENRE_MODEL = "genre_discogs400-discogs-effnet-1"
MODEL_BASE_URL = "https://essentia.upf.edu/models"
MODEL_FILES = {
    EMBEDDING_MODEL: "feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb",
    f"{GENRE_MODEL}.pb": "classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.pb",
    f"{GENRE_MODEL}.json": "classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.json",
}


def models_dir() -> Path:
    return get_settings().data_dir / "models"


def ensure_models() -> None:
    """Download the model files on first use (~20 MB)."""
    import ssl
    import urllib.request

    import certifi

    # python.org builds ship without root certificates: use certifi's bundle.
    context = ssl.create_default_context(cafile=certifi.where())
    target = models_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name, remote in MODEL_FILES.items():
        if not (target / name).exists():
            tmp = target / f"{name}.part"
            url = f"{MODEL_BASE_URL}/{remote}"
            with urllib.request.urlopen(url, context=context, timeout=120) as response:
                tmp.write_bytes(response.read())
            tmp.rename(target / name)


def style_name(label: str) -> str:
    """'Electronic---Tech House' -> 'Tech House'."""
    return label.split("---")[-1]


class StyleClassifier:
    """Loads TensorFlow graphs once; Essentia algorithms are not thread-safe, hence the lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @cached_property
    def _models(self):
        import essentia

        essentia.log.warningActive = False
        from essentia.standard import TensorflowPredict2D, TensorflowPredictEffnetDiscogs

        ensure_models()
        root = models_dir()
        classes = json.loads((root / f"{GENRE_MODEL}.json").read_text())["classes"]
        embedding = TensorflowPredictEffnetDiscogs(
            graphFilename=str(root / EMBEDDING_MODEL), output="PartitionedCall:1"
        )
        head = TensorflowPredict2D(
            graphFilename=str(root / f"{GENRE_MODEL}.pb"),
            input="serving_default_model_Placeholder",
            output="PartitionedCall:0",
        )
        return classes, embedding, head

    def classify(self, path: str | Path, top: int = 10) -> list[dict]:
        """Top styles averaged over the track: [{"style": "Tech House", "label": ..., "score": 0.31}]."""
        from essentia.standard import MonoLoader

        with self._lock:
            classes, embedding, head = self._models
            audio = MonoLoader(filename=str(path), sampleRate=16000, resampleQuality=4)()
            scores = head(embedding(audio)).mean(axis=0)
        best = np.argsort(scores)[::-1][:top]
        return [
            {"style": style_name(classes[i]), "label": classes[i], "score": round(float(scores[i]), 4)}
            for i in best
        ]


classifier = StyleClassifier()
