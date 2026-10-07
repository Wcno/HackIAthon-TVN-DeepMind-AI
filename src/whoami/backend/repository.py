"""SQLite owns live fiches, review history and generation cache.

JSONL inputs are seed data, never rewritten when a person reviews a case.
Each review uses an immediate transaction and an expected version.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from whoami.backend.pipeline import PipelineBundle
from whoami.contracts import REVIEW_STATES


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class MissingRecord(ValueError):
    pass


class ReviewConflict(ValueError):
    pass


class InvalidReview(ValueError):
    pass


REVIEW_TRANSITIONS = {
    "nuevo": {"en_revision", "descartado"},
    "en_revision": {"requiere_evidencia", "aprobado_como_borrador", "descartado"},
    "requiere_evidencia": {"en_revision", "descartado"},
    "aprobado_como_borrador": {"en_revision"},
    "descartado": {"en_revision"},
}


class EditorialRepository:
    def __init__(self, database: Path):
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY (kind, id)
                );
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL, content_hash TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    state TEXT NOT NULL, actor TEXT, timestamp TEXT NOT NULL,
                    note TEXT, version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS review_history ON reviews(case_id, timestamp, id);
                CREATE TABLE IF NOT EXISTS generation_cache (
                    key TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            if "active" not in {row["name"] for row in connection.execute("PRAGMA table_info(cases)")}:
                connection.execute("ALTER TABLE cases ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def import_bundle(self, bundle: PipelineBundle) -> None:
        groups = {group["id_grupo"]: group for group in bundle.groups}
        evidence = {item["id_evidencia"]: item for item in bundle.evidence}
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            incoming_cases = {case["id_caso"] for case in bundle.cases}
            for previous in connection.execute("SELECT * FROM cases WHERE active = 1").fetchall():
                if previous["id"] not in incoming_cases:
                    version = previous["version"] + 1
                    connection.execute("UPDATE cases SET active = 0, version = ? WHERE id = ?", (version, previous["id"]))
                    self._insert_review(connection, {
                        "id_caso": previous["id"], "estado": "requiere_evidencia", "responsable": None,
                        "fecha": datetime.now(UTC).isoformat(), "nota": "Case withdrawn from the active pipeline; approval revoked.",
                    }, version)
            for kind, rows, id_field in (
                ("group", bundle.groups, "id_grupo"),
                ("evidence", bundle.evidence, "id_evidencia"),
                ("answer", bundle.answers, "id_consulta"),
            ):
                connection.execute("DELETE FROM records WHERE kind = ?", (kind,))
                for row in rows:
                    body = {key: value for key, value in row.items() if key != "estado_revision"}
                    connection.execute("INSERT INTO records VALUES (?, ?, ?)", (kind, row[id_field], canonical_json(body)))
            for case in bundle.cases:
                body = {key: value for key, value in case.items() if key != "estado_revision"}
                group = groups[case["id_grupo"]]
                dependency = {key: value for key, value in group.items() if key != "estado_revision"}
                source_ids = set(case["ids_fuente"])
                source_ids.update(member["id_noticia"] for member in group["miembros"])
                source_ids.update(context["id_evidencia"] for context in group["contexto"])
                digest = content_hash({"case": body, "group": dependency,
                                       "evidence": {key: evidence[key] for key in source_ids}})
                existing = connection.execute("SELECT * FROM cases WHERE id = ?", (case["id_caso"],)).fetchone()
                if existing is None:
                    connection.execute("INSERT INTO cases(id, body, content_hash, version) VALUES (?, ?, ?, 1)",
                                       (case["id_caso"], canonical_json(body), digest))
                    seed = sorted((review for review in bundle.reviews if review["id_caso"] == case["id_caso"]),
                                  key=lambda review: datetime.fromisoformat(review["fecha"]))
                    for review in seed:
                        self._insert_review(connection, review, 1)
                elif existing["content_hash"] != digest or not existing["active"]:
                    version = existing["version"] + 1
                    connection.execute("UPDATE cases SET body = ?, content_hash = ?, version = ?, active = 1 WHERE id = ?",
                                       (canonical_json(body), digest, version, case["id_caso"]))
                    self._insert_review(connection, {
                        "id_caso": case["id_caso"], "estado": "en_revision", "responsable": None,
                        "fecha": datetime.now(UTC).isoformat(), "nota": "Pipeline content changed; human review required.",
                    }, version)

    @staticmethod
    def _insert_review(connection, review: dict, version: int) -> None:
        timestamp = datetime.fromisoformat(review["fecha"]).astimezone(UTC).isoformat(timespec="microseconds")
        connection.execute("INSERT INTO reviews(case_id, state, actor, timestamp, note, version) VALUES (?, ?, ?, ?, ?, ?)",
                           (review["id_caso"], review["estado"], review["responsable"], timestamp, review["nota"], version))

    def records(self, kind: str) -> list[dict]:
        with self.connection() as connection:
            return [json.loads(row["body"]) for row in connection.execute("SELECT body FROM records WHERE kind = ? ORDER BY id", (kind,))]

    def record(self, kind: str, record_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute("SELECT body FROM records WHERE kind = ? AND id = ?", (kind, record_id)).fetchone()
            if row is None:
                raise MissingRecord(f"Unknown {kind}: {record_id}")
            return json.loads(row["body"])

    @staticmethod
    def _current_review(connection, case_id: str):
        # Seed fixtures can have future dates. A committed decision on a newer case
        # version supersedes the seed; timestamps order records within that version.
        return connection.execute("SELECT * FROM reviews WHERE case_id = ? ORDER BY version DESC, timestamp DESC, id DESC LIMIT 1", (case_id,)).fetchone()

    def case(self, case_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id = ? AND active = 1", (case_id,)).fetchone()
            if row is None:
                raise MissingRecord(f"Unknown case: {case_id}")
            review = self._current_review(connection, case_id)
            return json.loads(row["body"]) | {"estado_revision": review["state"] if review else "nuevo", "version": row["version"]}

    def review_history(self, case_id: str) -> list[dict]:
        self.case(case_id)
        with self.connection() as connection:
            return [{"id_caso": row["case_id"], "estado": row["state"], "responsable": row["actor"],
                     "fecha": row["timestamp"], "nota": row["note"], "version": row["version"]}
                    for row in connection.execute("SELECT * FROM reviews WHERE case_id = ? ORDER BY version, timestamp, id", (case_id,))]

    def review(self, case_id: str, *, state: str, actor: str, note: str | None, expected_version: int) -> dict:
        if state not in REVIEW_STATES or not actor.strip():
            raise InvalidReview("A valid state and a human reviewer are required.")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cases WHERE id = ? AND active = 1", (case_id,)).fetchone()
            if row is None:
                raise MissingRecord(f"Unknown case: {case_id}")
            if row["version"] != expected_version:
                raise ReviewConflict("The case changed. Reload it before submitting a review.")
            current = self._current_review(connection, case_id)
            current_state = current["state"] if current else "nuevo"
            if state not in REVIEW_TRANSITIONS[current_state]:
                raise InvalidReview(f"Transition {current_state} -> {state} is not allowed.")
            if current_state in ("aprobado_como_borrador", "descartado") and not (note or "").strip():
                raise InvalidReview("Reopening a case requires a reason.")
            case = json.loads(row["body"])
            if state == "aprobado_como_borrador" and (case["estado_evidencia"] == "insuficiente" or case["borrador"] is None):
                raise InvalidReview("Approval requires a draft and evidence that is not insufficient.")
            version = row["version"] + 1
            connection.execute("UPDATE cases SET version = ? WHERE id = ?", (version, case_id))
            self._insert_review(connection, {"id_caso": case_id, "estado": state, "responsable": actor.strip(),
                                            "fecha": datetime.now(UTC).isoformat(), "nota": note}, version)
        return self.case(case_id)

    def cache_get(self, key: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT body FROM generation_cache WHERE key = ?", (key,)).fetchone()
            return json.loads(row["body"]) if row else None

    def cache_put(self, key: str, value: dict) -> None:
        with self.connection() as connection:
            connection.execute("INSERT OR REPLACE INTO generation_cache VALUES (?, ?, ?)",
                               (key, canonical_json(value), datetime.now(UTC).isoformat()))
