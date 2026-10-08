"""One command saves benchmark outputs, baselines, metrics and the full test run."""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from whoami.contracts import DATA, OUTPUTS, PROCESSED
from whoami.embeddings import MODEL_NAME, MODEL_REVISION
from whoami.evaluation.datasets import (
    BENCHMARK, MANIFEST, PAIR_LABELS, ROOT, TOPIC_LABELS, benchmark_reviews, label_subject, load_cases, load_evidence, read_records, sha256, subject_hash,
)
from whoami.evaluation.metrics import answer_metrics, latency, score_answer
from whoami.evaluation.tasks import SeededEmbedder, aligned_vectors, claim_evaluation, grouping_evaluation, topic_evaluation
from whoami.generation.case_files import NoGroundedClaims, TwoStepGenerator
from whoami.generation.evidence_index import LocalEmbedder, default_retrievers
from whoami.generation.prompting import CosineGate
from whoami.generation.query_box import answer_query
from whoami.ingest.output import write_json
from whoami.schemas import Answer, Group, sort_inbox

# Concrete executable checks, not a declaration that all T01-T10 passed.
ACCEPTANCE = {
    "T01": ["test_g7_t01_invalid_dates_and_nulls_do_not_block_valid_rows", "test_gdp_dots_in_source_become_null"],
    "T02": ["test_an_outlet_copying_a_release_takes_the_origin_of_the_earlier_member"],
    "T03": ["test_applying_recirculations_moves_the_publication_back_and_keeps_the_rest",
            "test_a_group_where_every_member_came_back_is_recirculated_and_uses_the_original_date"],
    "T04": ["test_official_answers_keep_their_period"],
    "T05": ["test_a_contradiction_needs_two_distinct_values_from_distinct_evidences"],
    "T06": ["test_the_cosine_gate_abstains_without_calling_the_model_when_nothing_resembles_the_query"],
    "T07": ["test_the_injection_stays_inside_the_user_message_and_the_system_prompt_is_fixed",
            "test_source_text_cannot_close_or_open_a_tag"],
    "T08": ["test_score_group_builds_the_score_with_a_justification_per_component",
            "test_duplicating_news_does_not_raise_the_score",
            "test_high_priority_with_insufficient_evidence_cannot_be_approved"],
    "T09": ["test_the_written_output_loads_and_passes_verify"],
    "T10": ["test_all_screens_and_saved_decisions_survive_real_process_restart"],
}


def write_jsonl(path: Path, records) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8", newline="\n")


def run_tests(output: Path) -> dict:
    report = output / "pytest.xml"
    environment = os.environ | {"WHOAMI_VALIDATION_REPORT": str(output / "http-runtime.json")}
    process = subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml", str(report)],
                             cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output / "pytest.log").write_text(process.stdout + process.stderr, encoding="utf-8")
    tests = []
    if report.exists():
        for item in ET.parse(report).iter("testcase"):
            status = "failed" if item.find("failure") is not None or item.find("error") is not None else "skipped" if item.find("skipped") is not None else "passed"
            tests.append({"name": item.attrib["name"], "class": item.attrib.get("classname"), "status": status})
    matrix = {
        identity: {"checks": names, "passed": all(any(test["name"] == name and test["status"] == "passed" for test in tests) for name in names)}
        for identity, names in ACCEPTANCE.items()
    }
    return {"exit_code": process.returncode, "counts": dict(Counter(item["status"] for item in tests)),
            "acceptance": matrix, "g10_note": "Local T10 runtime evidence is saved; the G10 demo/Notion delivery is separate."}


class MeasuredLLM:
    """Provider-reported token usage, separating network from cache replay."""

    def __init__(self, llm):
        self.llm = llm
        self.calls = []

    def complete(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            completion = self.llm.complete(*args, **kwargs)
        except Exception as error:
            self.calls.append({"purpose": kwargs.get("purpose"), "status": type(error).__name__,
                               "wall_s": time.perf_counter() - started})
            raise
        self.calls.append({"purpose": kwargs.get("purpose"), "status": "ok", "cached": completion.cached,
                           "prompt_tokens": completion.prompt_tokens, "completion_tokens": completion.completion_tokens,
                           "provider_latency_s": completion.latency_s, "wall_s": time.perf_counter() - started})
        return completion


def token_totals(calls: list[dict]) -> dict:
    successful = [call for call in calls if call["status"] == "ok"]
    return {
        "calls": len(calls), "errors": len(calls) - len(successful),
        "network_calls": sum(not call["cached"] for call in successful),
        "cache_hits": sum(call["cached"] for call in successful),
        "prompt_tokens": sum(call["prompt_tokens"] for call in successful),
        "completion_tokens": sum(call["completion_tokens"] for call in successful),
        "network_tokens": sum(call["prompt_tokens"] + call["completion_tokens"] for call in successful if not call["cached"]),
        "failed_request_tokens": None if len(successful) != len(calls) else 0,
        "cost": None, "cost_note": "Token usage is measured; no price is inferred from a free-tier quota.",
    }


def retrieval_benchmark(cases, retrievers, repeats: int) -> tuple[dict, list[dict]]:
    records = []
    names = list(retrievers)
    # Warm-up outside timing; per-query embedding time remains inside each measurement.
    for retriever in retrievers.values():
        retriever.search("contexto de Panamá", 8)
    for repeat in range(repeats):
        for number, case in enumerate(cases):
            order = names[number % len(names):] + names[:number % len(names)]
            for name in order:
                started = time.perf_counter()
                hits = retrievers[name].search(case.query, 8)
                duration = time.perf_counter() - started
                found = set(identity for identity, _ in hits)
                records.append({"id": case.id, "method": name, "repeat": repeat, "latency_s": duration,
                                "hits": [{"id": identity, "score": float(score)} for identity, score in hits],
                                "relevant_found": len(found & set(case.evidence_ids)), "relevant_total": len(case.evidence_ids)})
    metrics = {}
    for name in names:
        method = [record for record in records if record["method"] == name]
        judged = [record for record in method if record["relevant_total"]]
        numerator = sum(record["relevant_found"] for record in judged)
        denominator = sum(record["relevant_total"] for record in judged)
        metrics[name] = {
            "latency": latency([record["latency_s"] for record in method]),
            "micro_recall_at_8": {"numerator": numerator, "denominator": denominator,
                                  "value": numerator / denominator if denominator else None},
            "macro_recall_at_8": sum(record["relevant_found"] / record["relevant_total"] for record in judged) / len(judged) if judged else None,
            "judged_queries": len(judged) // repeats,
            "failures": sorted({record["id"] for record in judged if record["relevant_found"] != record["relevant_total"]}),
        }
    return metrics, records


def generate_cases(output: Path, evidence, llm, model: str, count: int) -> tuple[list[dict], list[dict]]:
    generator = TwoStepGenerator(llm, model)
    groups = sort_inbox([Group.model_validate(record) for record in read_records(PROCESSED / "grupos.jsonl")])
    cases, errors = [], []
    for group in [group for group in groups if group.estado_evidencia != "insuficiente"][:count]:
        print(f"G7: generating claims for {group.id_grupo}", flush=True)
        try:
            case, report, calls = generator.generate(group, evidence, f"CASO-{group.id_grupo[2:]}")
            cases.append(case.model_dump(mode="json"))
        except NoGroundedClaims as error:
            errors.append({"group": group.id_grupo, "error": type(error).__name__})
    write_jsonl(output / "fichas.jsonl", cases)
    return cases, errors


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--output", type=Path, default=OUTPUTS / "evaluation/g7")
    parser.add_argument("--reserved", type=Path, help="explicit jury package; the default run never reads it")
    parser.add_argument("--human-reviews", type=Path, help="folder with topics, pairs, claims and optional benchmark reviews (JSONL/CSV)")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--generate-cases", type=int, default=20)
    parser.add_argument("--reuse-generation", type=Path, help="rescore a saved run with original tokens/timings; no model calls")
    parser.add_argument("--skip-tests", action="store_true", help="reuse only while iterating; does not satisfy G7 acceptance")


def review_file(directory: Path | None, name: str, optional: bool = False) -> Path | None:
    if directory is None:
        return None
    candidates = [directory / f"{name}{suffix}" for suffix in (".jsonl", ".csv")]
    existing = [path for path in candidates if path.exists()]
    if optional and not existing:
        return None
    if len(existing) != 1:
        raise ValueError(f"Expected exactly one {name}.jsonl or {name}.csv in human review directory")
    return existing[0]


def validate_saved_inputs(saved: dict, expected: dict) -> None:
    for name, fingerprint in expected.items():
        if saved.get(name) != fingerprint:
            raise ValueError(f"Saved generation belongs to different or unverified {name}")


def evaluate(args) -> dict:
    if args.repeats < 1 or args.generate_cases < 0:
        raise ValueError("repeats must be positive and generate-cases nonnegative")
    output = args.output.resolve()
    if output in (ROOT.resolve(), OUTPUTS.resolve(), DATA.resolve()) or DATA.resolve() in output.parents:
        raise ValueError("Use a separate evaluation directory, not product data/output roots")
    if args.reuse_generation and args.reuse_generation.resolve() == output:
        raise ValueError("Replay output must differ from the original run directory")
    output.mkdir(parents=True, exist_ok=True)
    benchmark_path = args.reserved or BENCHMARK
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    split = "reserved" if args.reserved else "development"
    if sha256(benchmark_path) != manifest[split]["sha256"]:
        raise ValueError("Benchmark changed since the development/held-out split was frozen")
    cases = load_cases(benchmark_path, manifest[split]["count"])
    if dict(Counter(case.kind for case in cases)) != manifest[split]["by_kind"]:
        raise ValueError("Benchmark type distribution changed")
    evidence_path = PROCESSED / "evidencias.jsonl"
    evidence = load_evidence(evidence_path)
    corpus_fingerprint = subject_hash({identity: item.model_dump(mode="json") for identity, item in evidence.items()})
    missing = {identity for case in cases for identity in case.evidence_ids if identity not in evidence}
    if missing:
        raise ValueError(f"Expected benchmark evidence missing: {sorted(missing)}")
    if any(case.query in field for case in cases for item in evidence.values() for field in item.campos.values()):
        raise ValueError("Benchmark question leaked into evidence corpus")
    benchmark_review, benchmark_packet = benchmark_reviews(cases, evidence, review_file(args.human_reviews, "benchmark", optional=True))
    write_jsonl(output / "benchmark_review_packet.jsonl", benchmark_packet)
    vector_path = PROCESSED / "embeddings/embeddinggemma-300m-q4.npy"
    ids, vectors = aligned_vectors(vector_path, evidence)
    topics, topic_predictions = topic_evaluation(ids, vectors, evidence, review_file(args.human_reviews, "topics"))
    grouping, group_predictions = grouping_evaluation(ids, vectors, evidence, review_file(args.human_reviews, "pairs"))
    print(f"G7: {len(cases)} {split} queries, {len(evidence)} evidences, vectors aligned", flush=True)
    # Cache identity includes content, model and text recipe; it cannot reuse an old same-ID corpus.
    cache_key = subject_hash({"sources": [item.model_dump(mode="json") for item in evidence.values()],
                              "model": MODEL_NAME, "revision": MODEL_REVISION, "recipe_version": 2,
                              "news_vectors_sha256": sha256(vector_path)})
    cache = Path.home() / ".cache/whoami/evaluation" / cache_key / "evidence.npy"
    build_started = time.perf_counter()
    retrievers = default_retrievers(evidence.values(), SeededEmbedder(LocalEmbedder(), ids, vectors, evidence), cache)
    index_s = time.perf_counter() - build_started
    retrieval, retrieval_records = retrieval_benchmark(cases, retrievers, args.repeats)
    write_jsonl(output / "retrieval.jsonl", retrieval_records)
    write_jsonl(output / "topic_predictions.jsonl", topic_predictions)
    write_jsonl(output / "group_predictions.jsonl", group_predictions)
    llm = None
    saved = None
    saved_answers, saved_scores = {}, {}
    if args.reuse_generation:
        saved = json.loads((args.reuse_generation / "metrics.json").read_text(encoding="utf-8"))
        validate_saved_inputs(saved["inputs"], {
            "benchmark_sha256": sha256(benchmark_path), "evidence_sha256": sha256(evidence_path),
            "vectors_sha256": sha256(vector_path), "evaluation_corpus_sha256": corpus_fingerprint,
        })
        from whoami.evaluation.datasets import unique_records

        saved_answers = unique_records(read_records(args.reuse_generation / "answers.jsonl"), "id")
        saved_scores = unique_records(read_records(args.reuse_generation / "query_scores.jsonl"), "id")
        if set(saved_answers) != {case.id for case in cases} or set(saved_scores) != set(saved_answers):
            raise ValueError("Saved run must retain every benchmark query, including failures")
    elif args.mode == "live":
        from whoami.llm import default_llm
        llm = MeasuredLLM(default_llm())
    archive = {row["consulta"]: row for row in read_records(OUTPUTS / "consultas.jsonl")} if args.mode == "recorded" else {}
    gate = CosineGate(retrievers["emb"])
    results, answers = [], []
    for case in cases:
        print(f"G7: {args.mode} {case.id}", flush=True)
        started = time.perf_counter()
        before = len(llm.calls) if llm else 0
        if saved is not None:
            raw_answer = saved_answers[case.id]["answer"]
            answer = Answer.model_validate(raw_answer) if raw_answer is not None else None
            if answer is not None and answer.consulta != case.query:
                raise ValueError(f"Saved answer query differs: {case.id}")
        elif llm is not None:
            answer = answer_query(case.id, case.query, retrievers["hybrid"], gate, evidence, llm, args.model)
        elif case.query in archive:
            answer = Answer.model_validate(archive[case.query] | {"id_consulta": case.id})
        else:
            answer = None
        record = score_answer(case, answer, evidence)
        if llm and any(call["status"] != "ok" for call in llm.calls[before:]):
            record.update(state="error", returned_state=answer.estado, ok=False, safety=None)
        record["generation_wall_s"] = time.perf_counter() - started if llm else None
        record["calls"] = llm.calls[before:] if llm else None
        if saved is not None:
            record["generation_wall_s"] = saved_scores[case.id]["generation_wall_s"]
            record["calls"] = saved_scores[case.id]["calls"]
            if saved_scores[case.id]["state"] == "error":
                record.update(state="error", ok=False, safety=None)
        results.append(record)
        answers.append({"id": case.id, "answer": answer.model_dump(mode="json") if answer else None})
        # Save incrementally so interrupted live runs retain their evidence.
        write_jsonl(output / "answers.jsonl", answers)
        write_jsonl(output / "query_scores.jsonl", results)
    if saved is not None:
        generated, generation_errors = read_records(args.reuse_generation / "fichas.jsonl"), saved["generation_errors"]
        write_jsonl(output / "fichas.jsonl", generated)
    elif llm is not None and args.generate_cases:
        generated, generation_errors = generate_cases(output, evidence, llm, args.model, args.generate_cases)
    else:
        generated, generation_errors = read_records(OUTPUTS / "fichas.jsonl"), []
        write_jsonl(output / "fichas.jsonl", generated)
    claims, packet = claim_evaluation(generated, evidence, review_file(args.human_reviews, "claims"))
    write_jsonl(output / "claim_review_packet.jsonl", packet)
    for filename, path, identity in (("topic_review_packet.jsonl", TOPIC_LABELS, "id_noticia"), ("pair_review_packet.jsonl", PAIR_LABELS, "p")):
        kind = "topic" if identity == "id_noticia" else "pair"
        subjects = [(row, label_subject(row, kind, evidence)) for row in read_records(path)]
        write_jsonl(output / filename, [{"subject_id": str(row[identity]), "subject_hash": subject_hash(subject), "subject": subject,
                                        "label": "", "reviewer": "", "reviewed_at": ""} for row, subject in subjects])
    tests = {"skipped": True} if args.skip_tests else run_tests(output)
    prerequisites = {
        "all_queries_measured": not any(record["state"] in ("missing", "error") for record in results),
        "topics_human": topics["labels"]["provenance"] == "human",
        "pairs_human": grouping["labels"]["provenance"] == "human",
        "benchmark_human": benchmark_review["complete"],
        "human_claim_sample": claims["reviewed_unique_claims"] >= 30,
        "human_support_target": claims["meets_human_target"],
        "tests_and_acceptance": not args.skip_tests and tests["exit_code"] == 0 and all(item["passed"] for item in tests["acceptance"].values()),
    }
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(), "mode": "saved generation" if saved else args.mode, "split": split,
        "generation_origin": str(args.reuse_generation) if saved else None,
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
                        "embedding_threads": os.environ.get("WHOAMI_EMBEDDING_THREADS", "ONNX default")},
        "inputs": {"benchmark_sha256": sha256(benchmark_path), "evidence_sha256": sha256(evidence_path),
                   "vectors_sha256": sha256(vector_path), "evaluation_corpus_sha256": corpus_fingerprint,
                   "frozen_news": len(ids), "evidence_count": len(evidence)},
        "model": {"generation": saved["model"]["generation"] if saved else args.model if llm else "recorded product outputs; original timing/tokens unavailable",
                  "embedding": MODEL_NAME, "revision": MODEL_REVISION, "cosine_threshold": gate.min_cosine},
        "index_setup_s": index_s, "index_seeded_news": len(ids), "retrieval": retrieval, "answers": answer_metrics(cases, results),
        "generation_latency": latency([record["generation_wall_s"] for record in results if record["generation_wall_s"] is not None]),
        "tokens": saved["tokens"] if saved else token_totals(llm.calls) if llm else None,
        "network_calls_this_run": sum(not call.get("cached", True) for call in llm.calls if call["status"] == "ok") if llm else 0,
        "classification": topics, "grouping": grouping, "claims": claims, "benchmark_review": benchmark_review,
        "generation_errors": generation_errors,
        "tests": tests, "prerequisites": prerequisites, "complete": all(prerequisites.values()),
        "held_out": {"count": 20, "read": bool(args.reserved), "sha256": manifest["reserved"]["sha256"]},
    }
    write_json(output / "metrics.json", report)
    return report


def main(args) -> int:
    report = evaluate(args)
    print(json.dumps({"output": str(args.output), "complete": report["complete"], "prerequisites": report["prerequisites"],
                      "answers": report["answers"], "generation_latency": report["generation_latency"]}, indent=2, ensure_ascii=True))
    return 0 if report["complete"] else 2
