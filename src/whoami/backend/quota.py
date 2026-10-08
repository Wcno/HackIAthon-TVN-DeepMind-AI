"""Cross-process editor reservations combined with the project's shared ledger.

Reservations never expire from the budget on crashes; the quota day resets them.
SQLite transactions run in worker threads, never on the async event loop.
"""
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from whoami.llm.ledger import Ledger
from whoami.llm.models import MODELS, RATE_HEADROOM, TOKEN_HEADROOM, ModelLimits
from whoami.llm.ratelimit import WINDOW_S
from whoami.llm.settings import quota_day_start


# Project free-tier daily request limits documented in ADR-0001.
# MODELS caps are already smaller experimental budgets, not provider RPD.
DAILY_REQUEST_LIMITS = {"gemini-3.5-flash-lite": 500, "gemini-3.1-flash-lite": 500,
                        "gemma-4-26b-a4b-it": 14400}


class QuotaUnavailable(RuntimeError):
    pass


class GenerationQuota:
    def __init__(self, model: str, *, ledger_path: Path, database: Path,
                 limits: ModelLimits | None = None, budget_since: datetime | None = None,
                 daily_request_limit: int | None = None):
        self.model = model
        self.limits = limits or MODELS.get(model) or MODELS["gemini-3.5-flash-lite"]
        daily_limit = daily_request_limit or (self.limits.cap if limits is not None else DAILY_REQUEST_LIMITS.get(model, self.limits.cap))
        self.budget_cap = min(self.limits.cap, int(daily_limit * 0.4))
        self.path = Path(database)
        self.ledger_path = Path(ledger_path)
        self.ledger = Ledger(self.ledger_path, lambda: datetime.now(UTC))
        configured = os.environ.get("WHOAMI_BUDGET_SINCE")
        self.since = budget_since or (datetime.fromisoformat(configured) if configured else None)
        if self.since is not None and self.since.tzinfo is None:
            self.since = self.since.replace(tzinfo=UTC)
        if self.limits.kind != "chat" or min(self.limits.cap, self.limits.rpm, self.limits.tpm) < 1:
            raise ValueError("Generation requires positive chat model quota limits.")

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=0.1)
        connection.execute("CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, model TEXT, at REAL, tokens INTEGER)")
        return connection

    def reserve(self, tokens: int) -> str:
        now = datetime.now(UTC)
        since = self.since or quota_day_start(now)
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT at, tokens FROM reservations WHERE model = ? AND at >= ?", (self.model, min(since.timestamp(), now.timestamp() - WINDOW_S))).fetchall()
            # App rows in the ledger are represented by reservations, not added twice.
            external = []
            if self.ledger_path.exists():
                for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                    entry = json.loads(line)
                    if entry["model"] == self.model and entry["cache"] == "miss" and not entry["purpose"].startswith("editor-quota:"):
                        external.append(entry)
            spent = sum(at >= since.timestamp() for at, _ in rows)
            spent += sum(max(e.get("n_texts", 0), 1) if e["status"] == "ok" else 1 for e in external if datetime.fromisoformat(e["ts"]) >= since)
            if spent + 1 > self.budget_cap:
                raise QuotaUnavailable("The shared generation quota budget is exhausted.")
            recent = [(at, count, 1) for at, count in rows if at > now.timestamp() - WINDOW_S]
            recent += [(datetime.fromisoformat(e["ts"]).timestamp(), e["total_tokens"], max(e.get("n_texts", 0), 1)) for e in external if datetime.fromisoformat(e["ts"]) > now - timedelta(seconds=WINDOW_S)]
            if sum(units for _, _, units in recent) + 1 > max(int(self.limits.rpm * RATE_HEADROOM), 1) or sum(count for _, count, _ in recent) + tokens > max(int(self.limits.tpm * TOKEN_HEADROOM), 1):
                raise QuotaUnavailable("The shared generation quota rate limit is reached; try again later.")
            identifier = uuid.uuid4().hex
            connection.execute("INSERT INTO reservations VALUES (?, ?, ?, ?)", (identifier, self.model, now.timestamp(), tokens))
            return identifier

    def finish(self, identifier: str, *, status: str, latency: float,
               prompt_tokens: int = 0, completion_tokens: int = 0,
               total_tokens: int | None = None) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT tokens FROM reservations WHERE id = ?", (identifier,)).fetchone()
            total = row[0] if total_tokens is None else total_tokens
            connection.execute("UPDATE reservations SET tokens = ? WHERE id = ?", (total, identifier))
            self.ledger.record(model=self.model, purpose=f"editor-quota:{identifier}", cache="miss", status=status,
                               latency_s=latency, prompt_tokens=prompt_tokens,
                               completion_tokens=completion_tokens, total_tokens=total)
