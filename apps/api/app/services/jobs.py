"""Progress/state of the in-process background jobs (genre analysis, audio analysis)."""

from dataclasses import asdict, dataclass, field


@dataclass
class JobStatus:
    state: str = "idle"  # idle | running | completed | stopped | failed
    running: bool = False
    error: str | None = None
    phase: str | None = None
    scope: str | None = None  # folder the job is limited to (None: whole library)
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    current: str | None = None
    errors: list[str] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None
    stop_requested: bool = False

    def as_dict(self) -> dict:
        data = asdict(self) | {"error_count": len(self.errors), "errors": self.errors[-20:]}
        data.pop("stop_requested")
        return data
