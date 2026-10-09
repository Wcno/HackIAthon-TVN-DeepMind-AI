"""Explicit paths and runtime options for the local MVP."""

import os
import math
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from whoami.contracts import DEMO, OUTPUTS, PROCESSED
from whoami.llm.settings import find_env_file


def default_database() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return root / "whoami" / "editorial.sqlite3"


@dataclass(frozen=True)
class Settings:
    database: Path = field(default_factory=default_database)
    data_directory: Path = DEMO
    output_directory: Path = DEMO
    static_directory: Path | None = None
    demo: bool = True
    offline: bool = True
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_api_key: str = field(default="", repr=False)
    generation_timeout: float = 20.0
    generation_attempts: int = 3
    generation_daily_limit: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.generation_timeout) or self.generation_timeout <= 0 or self.generation_attempts < 1:
            raise ValueError("Generation requires a positive deadline and at least one attempt.")
        if self.generation_daily_limit is not None and self.generation_daily_limit < 1:
            raise ValueError("The provider daily request limit must be positive.")

    @classmethod
    def from_environment(cls) -> "Settings":
        env_file = Path(os.environ.get("WHOAMI_ENV_FILE") or find_env_file())
        environment = {key: value for key, value in dotenv_values(env_file).items() if value is not None} | dict(os.environ)
        demo = environment.get("WHOAMI_DEMO", "0") == "1"
        api_key = environment.get("GEMINI_API_KEY", "")
        database = default_database().with_name("demo.sqlite3") if demo else default_database()
        return cls(
            database=Path(environment.get("WHOAMI_DATABASE", database)),
            data_directory=Path(environment.get("WHOAMI_DATA_DIRECTORY", DEMO if demo else PROCESSED)),
            output_directory=Path(environment.get("WHOAMI_OUTPUT_DIRECTORY", DEMO if demo else OUTPUTS)),
            demo=demo,
            offline=environment.get("WHOAMI_OFFLINE", "0" if api_key else "1") == "1",
            gemini_model=environment.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            gemini_base_url=environment.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            gemini_api_key=api_key,
            generation_timeout=float(environment.get("WHOAMI_GENERATION_TIMEOUT", "20")),
            generation_attempts=int(environment.get("WHOAMI_GENERATION_ATTEMPTS", "3")),
            generation_daily_limit=int(environment["WHOAMI_GENERATION_DAILY_LIMIT"]) if environment.get("WHOAMI_GENERATION_DAILY_LIMIT") else None,
        )
