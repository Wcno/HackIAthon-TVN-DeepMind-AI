"""Append-only JSONL ledger of every LLM call, and the usage summary built from it."""

import argparse
import json
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from whoami.llm.settings import Settings

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_P95 = 95


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _is_miss(entry: dict[str, Any]) -> bool:
    return entry["cache"] == "miss"


def _quota_cost(entry: dict[str, Any]) -> int:
    """Chat attempts cost one call; an embedding batch costs one per text, a rejected attempt one unit."""
    if entry["status"] != "ok":
        return 1
    return max(entry["n_texts"], 1)


def _percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[percent - 1]


class Ledger:
    def __init__(self, path: Path, clock: Callable[[], datetime], *, provider_id: str | None = None) -> None:
        self._path = path
        self._clock = clock
        self._provider_id = provider_id

    def record(
        self,
        *,
        model: str,
        purpose: str,
        cache: Literal["hit", "miss"],
        status: str,
        latency_s: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        n_texts: int = 0,
    ) -> None:
        entry = {
            "ts": self._clock().astimezone(UTC).strftime(_TS_FORMAT),
            "model": model,
            "purpose": purpose,
            "cache": cache,
            "status": status,
            "latency_s": latency_s,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "n_texts": n_texts,
        }
        if self._provider_id is not None:
            entry["provider_id"] = self._provider_id
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def spent(self, model: str, since: datetime) -> int:
        return sum(
            _quota_cost(entry)
            for entry in self._entries(since)
            if entry["model"] == model and _is_miss(entry)
        )

    def recent_calls(self, model: str, since: datetime) -> list[tuple[datetime, int, int]]:
        """Network calls of a model since a moment, as `(time, tokens, units)`, so a new process can resume the
        rate limit where the previous one left it."""
        return [
            (_parse_ts(entry["ts"]), entry["total_tokens"], _quota_cost(entry))
            for entry in self._entries(since)
            if entry["model"] == model and _is_miss(entry)
        ]

    def summary(self, since: datetime | None = None) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in self._entries(since):
            grouped[entry["model"]].append(entry)
        return {model: _summarise(entries) for model, entries in grouped.items()}

    def _entries(self, since: datetime | None) -> Iterator[dict[str, Any]]:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if since is None or _parse_ts(entry["ts"]) >= since:
                yield entry


def _summarise(entries: list[dict[str, Any]]) -> dict[str, Any]:
    misses = [e for e in entries if _is_miss(e)]
    latencies = [e["latency_s"] for e in misses if e["status"] == "ok"]
    return {
        "calls": len(misses),
        "hits": len(entries) - len(misses),
        "errors": sum(e["status"] != "ok" for e in entries),
        "prompt_tokens": sum(e["prompt_tokens"] for e in entries),
        "completion_tokens": sum(e["completion_tokens"] for e in entries),
        "total_tokens": sum(e["total_tokens"] for e in entries),
        "texts": sum(e["n_texts"] for e in misses),
        "latency_p50_s": _percentile(latencies, 50),
        "latency_p95_s": _percentile(latencies, _P95),
    }


def format_summary(summary: dict[str, dict[str, Any]]) -> str:
    header = ["model", "calls", "hits", "errors", "prompt", "completion", "total", "texts", "p50 s", "p95 s"]
    rows = [
        [
            model,
            s["calls"],
            s["hits"],
            s["errors"],
            s["prompt_tokens"],
            s["completion_tokens"],
            s["total_tokens"],
            s["texts"],
            f"{s['latency_p50_s']:.2f}",
            f"{s['latency_p95_s']:.2f}",
        ]
        for model, s in sorted(summary.items())
    ]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise the LLM ledger.")
    parser.add_argument("--since", type=_parse_ts, help="ISO 8601 instant, e.g. 2026-10-07T07:00:00Z")
    args = parser.parse_args()
    ledger = Ledger(Settings.from_env().ledger_path, clock=lambda: datetime.now(UTC))
    print(format_summary(ledger.summary(args.since)))


if __name__ == "__main__":
    main()
