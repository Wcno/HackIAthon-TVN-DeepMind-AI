"""Writers shared by every builder, so processed files are encoded and formatted the same way."""

import csv
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path


def write_csv(path: Path, columns: tuple[str, ...], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, content: dict) -> None:
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def iso(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if value else ""
