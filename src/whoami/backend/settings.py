"""Explicit paths and runtime options for the local MVP."""

import os
import math
from dataclasses import dataclass, field
from pathlib import Path

from whoami.contracts import DEMO, OUTPUTS, PROCESSED


def default_database() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return root / "whoami" / "editorial.sqlite3"


@dataclass(frozen=True)
class Settings:
    database: Path = field(default_factory=default_database)
    data_directory: Path = DEMO
    output_directory: Path = DEMO
    demo: bool = True
    offline: bool = True
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_api_key: str = field(default="", repr=False)
    generation_timeout: float = 20.0
    generation_attempts: int = 3

    def __post_init__(self) -> None:
        if not math.isfinite(self.generation_timeout) or self.generation_timeout <= 0 or self.generation_attempts < 1:
            raise ValueError("Generation requires a positive deadline and at least one attempt.")

    @classmethod
    def from_environment(cls) -> "Settings":
        demo = os.environ.get("WHOAMI_DEMO", "1") == "1"
        return cls(
            database=Path(os.environ.get("WHOAMI_DATABASE", default_database())),
            data_directory=Path(os.environ.get("WHOAMI_DATA_DIRECTORY", DEMO if demo else PROCESSED)),
            output_directory=Path(os.environ.get("WHOAMI_OUTPUT_DIRECTORY", DEMO if demo else OUTPUTS)),
            demo=demo,
            offline=os.environ.get("WHOAMI_OFFLINE", "1") == "1",
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            gemini_base_url=os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            generation_timeout=float(os.environ.get("WHOAMI_GENERATION_TIMEOUT", "20")),
            generation_attempts=int(os.environ.get("WHOAMI_GENERATION_ATTEMPTS", "3")),
        )
