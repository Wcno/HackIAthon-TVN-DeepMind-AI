"""Frozen raw downloads (§7 `raw/`): untouched bytes plus a log of every fetch.

The log keeps the exact URL, SHA-256 and time of each fetch, which the manifest
needs to reproduce the snapshot. Builders read raw files only through this store.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from whoami.ingest.http import Response

FETCH_LOG = "_fetches.jsonl"


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str
    sha256: str
    fetched_at: datetime
    path: Path

    def read(self) -> bytes:
        return self.path.read_bytes()


class RawStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def save(self, name: str, response: Response, *, metadata: dict | None = None) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / name).write_bytes(response.body)
        entry = {
            "name": name,
            "url": response.url,
            "sha256": hashlib.sha256(response.body).hexdigest(),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        entry.update(metadata or {})
        with (self.directory / FETCH_LOG).open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def delete(self, prefix: str) -> None:
        """Drop files from a previous pull that a new full pull replaces."""
        for path in self.directory.glob(f"{prefix}*"):
            path.unlink()

    def append_record(self, name: str, record: dict) -> None:
        """For facts extracted at fetch time when the bytes themselves must not be kept."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / name).open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def records(self, name: str) -> list[dict]:
        path = self.directory / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def files(self) -> list[RawFile]:
        """Latest fetch of every file still on disk, oldest first."""
        log = self.directory / FETCH_LOG
        if not log.exists():
            return []
        latest = {}
        for line in log.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            latest[entry["name"]] = entry
        files = [
            RawFile(
                name=name,
                url=entry["url"],
                sha256=entry["sha256"],
                fetched_at=datetime.fromisoformat(entry["fetched_at"]),
                path=self.directory / name,
            )
            for name, entry in latest.items()
            if (self.directory / name).exists()
        ]
        return sorted(files, key=lambda file: file.fetched_at)


def capture_name() -> str:
    """Unique per fetch, so feeds that only show recent items accumulate history."""
    return f"capture_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.xml"
