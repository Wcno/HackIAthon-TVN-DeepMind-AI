"""Explicit evaluation inputs; neither gold labels nor held-out queries enter retrieval."""

import csv
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from whoami.contracts import DATA
from whoami.pipeline.topics import TOPIC_ORDER
from whoami.schemas import Evidence

ROOT = DATA.parent
BENCHMARK = DATA / "evaluation" / "benchmark.jsonl"
MANIFEST = DATA / "evaluation" / "manifest.json"
SYNTHETIC = ROOT / "experiments/g4/devset_sinteticas.jsonl"
TOPIC_LABELS = DATA / "labels/temas.jsonl"
PAIR_LABELS = ROOT / "experiments/g3/datos/pairs_gold.jsonl"


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1)
    kind: Literal["supported", "contradiction", "unanswerable", "adversarial"]
    query: str = Field(min_length=1)
    expected_states: tuple[Literal["respondida", "contradiccion", "abstencion"], ...] = Field(min_length=1)
    keys: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    safety_check: str | None = None
    synthetic: bool = False
    annotation: str = "agent proposal, pending human review"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def subject_hash(subject: dict) -> str:
    return hashlib.sha256(json.dumps(subject, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_records(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def unique_records(records: list[dict], key: str) -> dict[str, dict]:
    indexed = {str(record[key]): record for record in records}
    if len(indexed) != len(records):
        raise ValueError(f"Duplicate {key} in evaluation input")
    return indexed


def load_cases(path: Path, expected_count: int) -> list[BenchmarkCase]:
    cases = [BenchmarkCase.model_validate(record) for record in read_records(path)]
    if len(cases) != expected_count or len({case.id for case in cases}) != len(cases):
        raise ValueError(f"Expected {expected_count} unique benchmark cases")
    if len({case.query.casefold() for case in cases}) != len(cases):
        raise ValueError("Benchmark queries must be distinct")
    return cases


def load_evidence(path: Path) -> dict[str, Evidence]:
    records = read_records(path) + read_records(SYNTHETIC) + read_records(BENCHMARK.parent / "synthetic.jsonl")
    return {key: Evidence.model_validate(record) for key, record in unique_records(records, "id_evidencia").items()}


def label_subject(record: dict, kind: str, evidence: dict[str, Evidence]) -> dict:
    ids = [record["id_noticia"]] if kind == "topic" else [record["id_a"], record["id_b"]]
    return {"annotation": record, "sources": {identity: evidence[identity].model_dump(mode="json") for identity in ids}}


def apply_human_labels(
    records: list[dict], kind: str, review_path: Path | None, subject_for: Callable[[dict], dict] | None = None,
) -> tuple[list[dict], dict]:
    """Only decisions tied to the current subject bytes can replace proposed labels."""
    decisions = unique_records(read_records(review_path), "subject_id") if review_path else {}
    applied, failures, result = [], [], []
    for record in records:
        item = dict(record)
        identity = str(record["id_noticia"] if kind == "topic" else record["p"])
        review = decisions.get(identity)
        if review is not None:
            try:
                verify_review(review, subject_hash(subject_for(record) if subject_for else record))
                label = review["label"]
                if kind == "topic":
                    if label not in TOPIC_ORDER:
                        raise ValueError("Unknown topic")
                    item["tema"] = label
                else:
                    label = int(label)
                    if label not in (0, 1, 2):
                        raise ValueError("Pair label must be 0, 1 or 2")
                    item["etiqueta"] = label
                applied.append(identity)
            except (ValueError, KeyError, TypeError) as error:
                failures.append({"id": identity, "reason": str(error)})
        result.append(item)
    unknown = sorted(set(decisions) - {str(record["id_noticia"] if kind == "topic" else record["p"]) for record in records})
    return result, {
        "reviewed": len(applied), "total": len(records), "failures": failures, "unknown_ids": unknown,
        "provenance": "human" if len(applied) == len(records) and not failures and not unknown else "provisional agent labels",
    }


def verify_review(review: dict, expected_hash: str) -> None:
    reviewer = str(review.get("reviewer", "")).strip()
    if not reviewer or any(word in reviewer.casefold() for word in ("agent", "claude", "gemini", "chatgpt")):
        raise ValueError("Named human reviewer required")
    stamp = datetime.fromisoformat(review["reviewed_at"])
    if stamp.tzinfo is None:
        raise ValueError("Human review timestamp must include timezone")
    if stamp > datetime.now(UTC):
        raise ValueError("Human review timestamp cannot be in the future")
    if review["subject_hash"] != expected_hash:
        raise ValueError("Review refers to different subject content")


def benchmark_subject(case: BenchmarkCase, evidence: dict[str, Evidence], corpus_hash: str) -> dict:
    return {"case": case.model_dump(mode="json"), "corpus_hash": corpus_hash,
            "sources": {identity: evidence[identity].model_dump(mode="json") for identity in case.evidence_ids}}


def benchmark_reviews(cases, evidence, path: Path | None) -> tuple[dict, list[dict]]:
    decisions = unique_records(read_records(path), "subject_id") if path else {}
    corpus_hash = subject_hash({identity: item.model_dump(mode="json") for identity, item in evidence.items()})
    reviewed, errors, packet = [], [], []
    for case in cases:
        subject = benchmark_subject(case, evidence, corpus_hash)
        packet.append({"subject_id": case.id, "subject_hash": subject_hash(subject), "subject": subject,
                       "reviewer": "", "reviewed_at": "", "verdict": ""})
        if case.id not in decisions:
            continue
        try:
            review = decisions[case.id]
            verify_review(review, subject_hash(subject))
            if review["verdict"] != "accepted":
                raise ValueError("Benchmark proposal was not accepted; correct and version it before another run")
            reviewed.append(case.id)
        except (ValueError, KeyError, TypeError) as error:
            errors.append({"id": case.id, "reason": str(error)})
    return {"reviewed": len(reviewed), "total": len(cases), "errors": errors,
            "complete": len(reviewed) == len(cases) and not errors,
            "unknown_ids": sorted(set(decisions) - {case.id for case in cases})}, packet
