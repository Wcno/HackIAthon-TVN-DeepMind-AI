"""Explicit paths and runtime options for the local MVP."""

import os
import math
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

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
    generation_provider: str = "gemini"
    qvac_base_url: str = "http://127.0.0.1:11435/v1/"
    qvac_model: str = "g10-generator"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_api_key: str = field(default="", repr=False)
    generation_timeout: float = 20.0
    generation_attempts: int = 3
    generation_daily_limit: int | None = None

    def __post_init__(self) -> None:
        if self.generation_provider not in {"gemini", "qvac"}:
            raise ValueError("Unknown generation provider.")
        if self.generation_provider == "qvac":
            url = urlsplit(self.qvac_base_url)
            if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1"}
                    or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1"):
                raise ValueError("QVAC requires an HTTP loopback endpoint under /v1.")
            if not self.offline or not self.qvac_model.strip():
                raise ValueError("QVAC requires offline mode and an explicit model alias.")
        if not math.isfinite(self.generation_timeout) or self.generation_timeout <= 0 or self.generation_attempts < 1:
            raise ValueError("Generation requires a positive deadline and at least one attempt.")
        if self.generation_daily_limit is not None and self.generation_daily_limit < 1:
            raise ValueError("The provider daily request limit must be positive.")

    @property
    def cached_only(self) -> bool:
        return self.offline and self.generation_provider != "qvac"

    @property
    def generation_model(self) -> str:
        return self.qvac_model if self.generation_provider == "qvac" else self.gemini_model

    @classmethod
    def from_environment(cls) -> "Settings":
        env_file = Path(os.environ.get("WHOAMI_ENV_FILE") or find_env_file())
        environment = {key: value for key, value in dotenv_values(env_file).items() if value is not None} | dict(os.environ)
        demo = environment.get("WHOAMI_DEMO", "0") == "1"
        api_key = environment.get("GEMINI_API_KEY", "")
        provider = environment.get("WHOAMI_GENERATION_PROVIDER", "gemini")
        database = default_database().with_name("demo.sqlite3") if demo else default_database()
        return cls(
            database=Path(environment.get("WHOAMI_DATABASE", database)),
            data_directory=Path(environment.get("WHOAMI_DATA_DIRECTORY", DEMO if demo else PROCESSED)),
            output_directory=Path(environment.get("WHOAMI_OUTPUT_DIRECTORY", DEMO if demo else OUTPUTS)),
            demo=demo,
            offline=environment.get("WHOAMI_OFFLINE", "1" if provider == "qvac" or not api_key else "0") == "1",
            generation_provider=provider,
            qvac_base_url=environment.get("WHOAMI_QVAC_BASE_URL", "http://127.0.0.1:11435/v1/"),
            qvac_model=environment.get("WHOAMI_QVAC_MODEL", "g10-generator"),
            gemini_model=environment.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            gemini_base_url=environment.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            gemini_api_key=api_key,
            generation_timeout=float(environment.get("WHOAMI_GENERATION_TIMEOUT", "180" if provider == "qvac" else "20")),
            generation_attempts=int(environment.get("WHOAMI_GENERATION_ATTEMPTS", "3")),
            generation_daily_limit=int(environment["WHOAMI_GENERATION_DAILY_LIMIT"]) if environment.get("WHOAMI_GENERATION_DAILY_LIMIT") else None,
        )
