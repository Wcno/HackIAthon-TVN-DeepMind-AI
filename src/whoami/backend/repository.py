"""SQLite owns live fiches, review history and generation cache.

JSONL inputs are seed data, never rewritten when a person reviews a case.
Each review uses an immediate transaction and an expected version.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from whoami.backend.pipeline import PipelineBundle
from whoami.contracts import REVIEW_STATES, REVIEW_TRANSITIONS


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


def cited_ids(case: dict) -> list[str]:
    return list(dict.fromkeys(citation["id_evidencia"] for claim in case["afirmaciones"] for citation in claim["citas"]))


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
                    active INTEGER NOT NULL DEFAULT 1,
                    content_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS edited_drafts (
                    case_id TEXT PRIMARY KEY REFERENCES cases(id), body TEXT NOT NULL,
                    source_ids TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    state TEXT NOT NULL, actor TEXT, timestamp TEXT NOT NULL,
                    note TEXT, version INTEGER NOT NULL,
                    content_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS review_history ON reviews(case_id, timestamp, id);
                CREATE TABLE IF NOT EXISTS generation_cache (
                    key TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS generated_cases (
                    id TEXT PRIMARY KEY, group_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    reason TEXT NOT NULL, timestamp TEXT NOT NULL, content_version INTEGER NOT NULL
                );
            """)
            if "active" not in {row["name"] for row in connection.execute("PRAGMA table_info(cases)")}:
                connection.execute("ALTER TABLE cases ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
            for table in ("cases", "reviews"):
                if "content_version" not in {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN content_version INTEGER NOT NULL DEFAULT 1")

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
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            bundle = self._with_generated_cases(connection, bundle)
            groups = {group["id_grupo"]: group for group in bundle.groups}
            evidence = {item["id_evidencia"]: item for item in bundle.evidence}
            incoming_cases = {case["id_caso"] for case in bundle.cases}
            for previous in connection.execute("SELECT * FROM cases WHERE active = 1").fetchall():
                if previous["id"] not in incoming_cases:
                    version = previous["version"] + 1
                    content_version = previous["content_version"] + 1
                    connection.execute("UPDATE cases SET active = 0, version = ?, content_version = ? WHERE id = ?",
                                       (version, content_version, previous["id"]))
                    self._insert_audit(connection, previous["id"], "Case withdrawn from the active pipeline; approval revoked.", content_version)
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
                self._import_case(connection, case, groups[case["id_grupo"]], evidence.__getitem__, bundle.reviews)

    @staticmethod
    def _with_generated_cases(connection, bundle: PipelineBundle) -> PipelineBundle:
        """Adds the case files generated live to the committed bundle; one the bundle now ships for the same group wins."""
        shipped = {case["id_grupo"] for case in bundle.cases}
        known = {group["id_grupo"] for group in bundle.groups}
        generated = []
        for row in connection.execute("SELECT * FROM generated_cases").fetchall():
            if row["group_id"] in shipped or row["group_id"] not in known:
                connection.execute("DELETE FROM generated_cases WHERE id = ?", (row["id"],))
            else:
                generated.append(json.loads(row["body"]))
        case_of_group = {case["id_grupo"]: case["id_caso"] for case in generated}
        return replace(bundle, cases=(*bundle.cases, *generated),
                       groups=tuple(group | {"id_caso": case_of_group[group["id_grupo"]]} if group["id_grupo"] in case_of_group else group
                                    for group in bundle.groups))

    def add_generated_case(self, case: dict) -> str:
        """Stores a case file generated live for a group that had none, in this database only, and returns its id.

        A group that already has a case file keeps it, so repeating the call is harmless."""
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT body FROM records WHERE kind = 'group' AND id = ?", (case["id_grupo"],)).fetchone()
            if row is None:
                raise MissingRecord(f"Unknown group: {case['id_grupo']}")
            group = json.loads(row["body"])
            if group["id_caso"]:
                return group["id_caso"]
            connection.execute("INSERT INTO generated_cases VALUES (?, ?, ?, ?)",
                               (case["id_caso"], case["id_grupo"], canonical_json(case), datetime.now(UTC).isoformat()))
            group["id_caso"] = case["id_caso"]
            connection.execute("UPDATE records SET body = ? WHERE kind = 'group' AND id = ?", (canonical_json(group), case["id_grupo"]))

            def evidence_of(evidence_id: str) -> dict:
                found = connection.execute("SELECT body FROM records WHERE kind = 'evidence' AND id = ?", (evidence_id,)).fetchone()
                if found is None:
                    raise MissingRecord(f"Unknown evidence: {evidence_id}")
                return json.loads(found["body"])

            self._import_case(connection, case, group, evidence_of, ())
        return case["id_caso"]

    def _import_case(self, connection, case: dict, group: dict, evidence_of: Callable[[str], dict], reviews) -> None:
        body = {key: value for key, value in case.items() if key != "estado_revision"}
        dependency = {key: value for key, value in group.items() if key != "estado_revision"}
        source_ids = set(cited_ids(case))
        source_ids.update(member["id_noticia"] for member in group["miembros"])
        source_ids.update(context["id_evidencia"] for context in group["contexto"])
        source_ids.update(version["id_evidencia"] for contradiction in case["contradicciones"]
                          for version in contradiction["versiones"])
        digest = content_hash({"case": body, "group": dependency,
                               "evidence": {key: evidence_of(key) for key in source_ids}})
        existing = connection.execute("SELECT * FROM cases WHERE id = ?", (case["id_caso"],)).fetchone()
        if existing is None:
            connection.execute("INSERT INTO cases(id, body, content_hash, version) VALUES (?, ?, ?, 1)",
                               (case["id_caso"], canonical_json(body), digest))
            seed = sorted((review for review in reviews if review["id_caso"] == case["id_caso"]),
                          key=lambda review: datetime.fromisoformat(review["fecha"]))
            # Demo review dates are synthetic and may be later today.
            # Anchor that simulated history before import time, preserving
            # source timestamps in notes. Real human decisions use real UTC.
            now = datetime.now(UTC)
            shift = timedelta(0)
            if seed and case.get("sintetico"):
                latest = datetime.fromisoformat(seed[-1]["fecha"])
                if latest >= now:
                    shift = latest - now + timedelta(seconds=1)
            for review in seed:
                if shift:
                    review = review | {"fecha": (datetime.fromisoformat(review["fecha"]) - shift).isoformat(),
                                       "nota": (review["nota"] or "") + f" [Synthetic seed date {review['fecha']} anchored at import.]"}
                self._insert_review(connection, review, 1)
        elif existing["content_hash"] != digest or not existing["active"]:
            version = existing["version"] + 1
            content_version = existing["content_version"] + 1
            connection.execute("UPDATE cases SET body = ?, content_hash = ?, version = ?, active = 1, content_version = ? WHERE id = ?",
                               (canonical_json(body), digest, version, content_version, case["id_caso"]))
            self._insert_audit(connection, case["id_caso"], "Pipeline content changed; human review required.", content_version)

    @staticmethod
    def _insert_audit(connection, case_id: str, reason: str, content_version: int) -> None:
        connection.execute("INSERT INTO audit_events(case_id, reason, timestamp, content_version) VALUES (?, ?, ?, ?)",
                           (case_id, reason, datetime.now(UTC).isoformat(), content_version))

    @staticmethod
    def _insert_review(connection, review: dict, version: int) -> None:
        timestamp = datetime.fromisoformat(review["fecha"]).astimezone(UTC).isoformat(timespec="microseconds")
        content_version = connection.execute("SELECT content_version FROM cases WHERE id = ?", (review["id_caso"],)).fetchone()[0]
        connection.execute("INSERT INTO reviews(case_id, state, actor, timestamp, note, version, content_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (review["id_caso"], review["estado"], review["responsable"], timestamp, review["nota"], version, content_version))

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
        # Decisions apply only to the content version that was reviewed.
        return connection.execute("""SELECT reviews.* FROM reviews JOIN cases ON cases.id = reviews.case_id
                                  WHERE case_id = ? AND reviews.content_version = cases.content_version
                                  ORDER BY timestamp DESC, reviews.id DESC LIMIT 1""", (case_id,)).fetchone()

    def case(self, case_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id = ? AND active = 1", (case_id,)).fetchone()
            if row is None:
                raise MissingRecord(f"Unknown case: {case_id}")
            review = self._current_review(connection, case_id)
            case = json.loads(row["body"])
            edited = connection.execute("SELECT * FROM edited_drafts WHERE case_id = ?", (case_id,)).fetchone()
            extra_sources = []
            if edited is not None:
                case["borrador"] = json.loads(edited["body"])
                extra_sources = json.loads(edited["source_ids"])
            group_record = connection.execute("SELECT body FROM records WHERE kind = 'group' AND id = ?", (case["id_grupo"],)).fetchone()
            if group_record is None:
                raise MissingRecord(f"The group of case {case_id} is no longer available.")
            group = json.loads(group_record["body"])
            return case | {"titulo": group["titulo"], "tema": group["tema"], "estado_evidencia": group["estado_evidencia"],
                           "puntaje": group["puntaje"]["valor"], "componentes": group["puntaje"]["componentes"],
                           "ids_fuente": list(dict.fromkeys([*cited_ids(case), *extra_sources])), "estado_revision": review["state"] if review else "nuevo",
                           "version": row["version"], "content_version": row["content_version"]}

    def save_draft(self, case_id: str, *, draft: dict, source_ids: list[str], expected_version: int) -> dict:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cases WHERE id = ? AND active = 1", (case_id,)).fetchone()
            if row is None:
                raise MissingRecord(f"Unknown case: {case_id}")
            if row["version"] != expected_version:
                raise ReviewConflict("La ficha cambió. Recarga antes de guardar para no sobrescribir otra edición.")
            seed = json.loads(row["body"])
            if seed["borrador"] is None or draft["leyenda"] != seed["borrador"]["leyenda"]:
                raise InvalidReview("No se puede crear un borrador sin evidencia ni cambiar su leyenda de alcance.")
            for source_id in source_ids:
                if connection.execute("SELECT 1 FROM records WHERE kind = 'evidence' AND id = ?", (source_id,)).fetchone() is None:
                    raise MissingRecord(f"Fuente no disponible: {source_id}")
            connection.execute("INSERT OR REPLACE INTO edited_drafts VALUES (?, ?, ?)",
                               (case_id, canonical_json(draft), canonical_json(list(dict.fromkeys(source_ids)))))
            connection.execute("UPDATE cases SET version = version + 1, content_version = content_version + 1 WHERE id = ?", (case_id,))
            self._insert_audit(connection, case_id, "Editorial draft edited; human review required.", row["content_version"] + 1)
        return self.case(case_id)

    def review_history(self, case_id: str) -> list[dict]:
        self.case(case_id)
        with self.connection() as connection:
            return [{"id_caso": row["case_id"], "estado": row["state"], "responsable": row["actor"],
                     "fecha": row["timestamp"], "nota": row["note"], "version": row["version"],
                     "content_version": row["content_version"]}
                    for row in connection.execute("SELECT * FROM reviews WHERE case_id = ? ORDER BY version, timestamp, id", (case_id,))]

    def current_review_records(self, case_id: str) -> list[dict]:
        """G2-compatible human history for the current content version only."""
        current_version = self.case(case_id)["content_version"]
        return [{key: value for key, value in review.items() if key not in ("version", "content_version")}
                for review in self.review_history(case_id) if review["content_version"] == current_version]

    def audit_history(self, case_id: str) -> list[dict]:
        self.case(case_id)
        with self.connection() as connection:
            return [dict(row) for row in connection.execute("SELECT reason, timestamp, content_version FROM audit_events WHERE case_id = ? ORDER BY id", (case_id,))]

    def review(self, case_id: str, *, state: str, actor: str, note: str | None, expected_version: int) -> dict:
        note = note.strip() or None if note is not None else None
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
            if state == "en_revision" and current_state in ("aprobado_como_borrador", "descartado") and not (note or "").strip():
                raise InvalidReview("Reopening a case requires a reason.")
            case = json.loads(row["body"])
            group_record = connection.execute("SELECT body FROM records WHERE kind = 'group' AND id = ?", (case["id_grupo"],)).fetchone()
            if group_record is None:
                raise MissingRecord(f"The group of case {case_id} is no longer available.")
            group = json.loads(group_record["body"])
            if state == "aprobado_como_borrador" and (group["estado_evidencia"] == "insuficiente" or case["borrador"] is None):
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

    def cache_delete(self, key: str) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM generation_cache WHERE key = ?", (key,))

    def snapshot_export(self) -> tuple[PipelineBundle, tuple[dict, ...]]:
        """Atomically separate strict seeds from human overlays and their reviews."""
        with self.connection() as connection:
            connection.execute("BEGIN")
            records = {kind: tuple(json.loads(row["body"]) for row in connection.execute(
                "SELECT body FROM records WHERE kind = ? ORDER BY id", (kind,)))
                for kind in ("group", "evidence", "answer")}
            cases = tuple(json.loads(row["body"]) for row in connection.execute(
                "SELECT body FROM cases WHERE active = 1 ORDER BY id"))
            current_reviews = tuple({
                "id_caso": row["case_id"], "estado": row["state"], "responsable": row["actor"],
                "fecha": row["timestamp"], "nota": row["note"], "version": row["version"],
                "content_version": row["content_version"],
            } for row in connection.execute("""
                SELECT reviews.* FROM reviews JOIN cases ON cases.id = reviews.case_id
                WHERE cases.active = 1 AND reviews.content_version = cases.content_version
                ORDER BY reviews.timestamp, reviews.id
            """))
            overlays = []
            for row in connection.execute("""
                SELECT edited_drafts.*, cases.version, cases.content_version
                FROM edited_drafts JOIN cases ON cases.id = edited_drafts.case_id
                WHERE cases.active = 1 ORDER BY cases.id
            """):
                reviews = [review for review in current_reviews if review["id_caso"] == row["case_id"]]
                overlays.append({
                    "id_caso": row["case_id"], "draft": json.loads(row["body"]),
                    "source_ids": json.loads(row["source_ids"]), "version": row["version"],
                    "content_version": row["content_version"], "reviews": reviews,
                    "review_state": reviews[-1]["estado"] if reviews else "nuevo",
                })
            edited_ids = {overlay["id_caso"] for overlay in overlays}
            seed_reviews = tuple({key: value for key, value in review.items()
                                  if key not in ("version", "content_version")}
                                 for review in current_reviews if review["id_caso"] not in edited_ids)
            return (PipelineBundle(records["group"], records["evidence"], cases,
                                   records["answer"], seed_reviews), tuple(overlays))

    def snapshot_bundle(self) -> PipelineBundle:
        """Read current pipeline content and matching human decisions atomically."""
        with self.connection() as connection:
            connection.execute("BEGIN")
            records = {kind: tuple(json.loads(row["body"]) for row in connection.execute(
                "SELECT body FROM records WHERE kind = ? ORDER BY id", (kind,)))
                for kind in ("group", "evidence", "answer")}
            cases = tuple(json.loads(row["body"]) for row in connection.execute(
                "SELECT body FROM cases WHERE active = 1 ORDER BY id"))
            reviews = tuple({"id_caso": row["case_id"], "estado": row["state"], "responsable": row["actor"],
                             "fecha": row["timestamp"], "nota": row["note"]}
                            for row in connection.execute("""
                                SELECT reviews.* FROM reviews JOIN cases ON cases.id = reviews.case_id
                                WHERE cases.active = 1 AND reviews.content_version = cases.content_version
                                ORDER BY reviews.timestamp, reviews.id
                            """))
            return PipelineBundle(records["group"], records["evidence"], cases, records["answer"], reviews)
