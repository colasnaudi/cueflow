from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://cueflow:cueflow@localhost:5433/cueflow"
    music_root: str = str(Path.home() / "Music")
    data_dir: Path = REPO_ROOT / "data"
    cors_origins: list[str] = ["http://localhost:3000"]
    # Application data living in the music folder (sampler packs, DAW libraries): never indexed.
    scan_exclude_dirs: list[str] = ["rekordbox", "Ableton", "_Serato_", "Native Instruments", "Logic"]

    # Parallel processes for library-wide audio analysis (each holds Essentia + a beat model, ~0.5 GB).
    analysis_workers: int = 3
    # Shift (ms) applied to MP3 cue/grid positions in the Rekordbox export: decoders disagree by about one MP3
    # frame (26 ms) depending on the LAME header. Measure it on your library before changing it.
    rekordbox_mp3_offset_ms: float = 0.0
    # The DJ's choice: generated cues are approved right away (edited later in Rekordbox if needed).
    auto_approve_cues: bool = True
    # The XML file Rekordbox is pointed at once (Preferences > Advanced > Database > rekordbox xml).
    # Default: data/rekordbox/cueflow.xml in the repository.
    rekordbox_xml_path: str | None = None

    ollama_url: str = "http://localhost:11434"
    ollama_llm_model: str = "gemma4:12b-it-qat"
    ollama_embed_model: str = "embeddinggemma"
    embedding_dim: int = 768


@lru_cache
def get_settings() -> Settings:
    return Settings()


def music_root() -> Path:
    return Path(get_settings().music_root).expanduser().resolve()
