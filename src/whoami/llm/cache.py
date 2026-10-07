"""On-disk response cache shared by concurrent worktrees (atomic writes)."""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class ResponseCache:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @staticmethod
    def key(payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get(self, key: str) -> dict | None:
        try:
            value = json.loads(self._path(key).read_text())
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: dict) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(value, file, ensure_ascii=False)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _path(self, key: str) -> Path:
        return self._directory / key[:2] / f"{key}.json"
