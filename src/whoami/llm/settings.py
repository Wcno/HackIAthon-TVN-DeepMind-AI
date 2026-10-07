"""Paths and environment for the LLM layer."""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from whoami.contracts import DATA

PROJECT_ROOT: Final = DATA.parent
QUOTA_TIMEZONE: Final = ZoneInfo("America/Los_Angeles")
DEFAULT_BASE_URL: Final = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GITDIR_PREFIX: Final = "gitdir:"
_WORKTREES_MARKER: Final = "/.git/worktrees/"


def quota_day_start(now: datetime) -> datetime:
    """Latest midnight in Los Angeles (when Gemini daily quotas reset), as UTC."""
    local = now.astimezone(QUOTA_TIMEZONE)
    midnight = datetime(local.year, local.month, local.day, tzinfo=QUOTA_TIMEZONE)
    return midnight.astimezone(UTC)


def find_env_file(root: Path = PROJECT_ROOT) -> Path:
    """`root/.env`, or the main checkout's `.env` when `root` is a git worktree."""
    env_file = root / ".env"
    git_entry = root / ".git"
    if env_file.exists() or not git_entry.is_file():
        return env_file
    pointer = git_entry.read_text().strip()
    if pointer.startswith(_GITDIR_PREFIX) and _WORKTREES_MARKER in pointer:
        main = pointer.removeprefix(_GITDIR_PREFIX).strip().split(_WORKTREES_MARKER)[0]
        return Path(main) / ".env"
    return env_file


@dataclass(frozen=True)
class Settings:
    env_file: Path
    cache_dir: Path
    ledger_path: Path
    budget_since: datetime
    base_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        budget_since = os.environ.get("WHOAMI_BUDGET_SINCE")
        return cls(
            env_file=Path(os.environ.get("WHOAMI_ENV_FILE") or find_env_file()),
            cache_dir=Path(os.environ.get("WHOAMI_LLM_CACHE") or Path.home() / ".cache/whoami/llm"),
            ledger_path=Path(os.environ.get("WHOAMI_LEDGER") or Path.home() / ".cache/whoami/ledger.jsonl"),
            budget_since=(
                datetime.fromisoformat(budget_since) if budget_since else quota_day_start(datetime.now(UTC))
            ),
            base_url=os.environ.get("GEMINI_BASE_URL") or DEFAULT_BASE_URL,
        )
