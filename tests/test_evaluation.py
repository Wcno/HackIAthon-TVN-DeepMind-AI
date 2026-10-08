"""Evaluation cannot hide missing cases, relabel machine outputs as human, or leak gold."""

import json
import csv
from pathlib import Path

import numpy as np
import pytest

from generation_fakes import FakeLLM, by_id, news
from whoami.evaluation.datasets import (
    BENCHMARK, MANIFEST, BenchmarkCase, apply_human_labels, benchmark_reviews, load_cases, load_evidence, sha256, subject_hash, verify_review,
)
from whoami.evaluation.metrics import answer_metrics, binary_counts, key_present, latency, ratio, score_answer
from whoami.evaluation.run import MeasuredLLM, evaluate, retrieval_benchmark, token_totals, validate_saved_inputs
from whoami.evaluation.tasks import SeededEmbedder, aligned_vectors, claim_evaluation, claim_subject
from whoami.embeddings import MODEL_NAME, MODEL_REVISION
from whoami.generation.prompting import CosineGate
from whoami.generation.query_box import answer_query
from whoami.schemas import Answer, Citation


def case(identity="Q-1", kind="supported", **changes):
    expected = ["abstencion"] if kind in ("unanswerable", "adversarial") else ["contradiccion"] if kind == "contradiction" else ["respondida"]
    return BenchmarkCase.model_validate({"id": identity, "kind": kind, "query": "¿Cuántos tránsitos?",
                                         "expected_states": expected, **changes})


def test_missing_benchmark_outputs_remain_in_the_denominator():
    cases = [case("A"), case("B")]
    records = [{"id": "A", "ok": True, "state": "respondida", "safety": True, "citations_valid": True},
               {"id": "B", "ok": False, "state": "missing", "safety": None, "citations_valid": None}]
    measured = answer_metrics(cases, records)
    assert measured["correct"] == {"numerator": 1, "denominator": 2, "value": 0.5, "failures": ["B"]}
    assert measured["missing"] == ["B"]
    with pytest.raises(ValueError, match="exactly one"):
        answer_metrics(cases, records[:1])


def test_correct_and_wrong_abstentions_use_distinct_populations():
    cases = [case("A"), case("B"), case("N", kind="unanswerable")]
    records = [{"id": item.id, "ok": item.id == "N", "state": "abstencion", "safety": True, "citations_valid": False} for item in cases]
    measured = answer_metrics(cases, records)
    assert measured["correct_abstentions"]["numerator"] == measured["correct_abstentions"]["denominator"] == 1
    assert measured["wrong_abstentions"] == {"numerator": 2, "denominator": 2, "value": 1, "case_ids": ["A", "B"]}
    assert measured["answer_citation_coverage"]["value"] is None


def test_provider_errors_cannot_count_as_correct_abstentions():
    measured = answer_metrics([case("N", kind="unanswerable")],
                             [{"id": "N", "ok": False, "state": "error", "safety": None, "citations_valid": False}])
    assert measured["correct_abstentions"]["numerator"] == 0
    assert measured["errors"] == ["N"]


def test_empty_samples_are_unavailable_not_perfect_or_zero():
    assert ratio([], [])["value"] is None
    assert latency([])["median_s"] is None
    assert latency([])["p95_s"] is None


def test_latency_nearest_rank_preserves_a_slow_tail():
    measured = latency(list(range(1, 21)))
    assert measured == {"n": 20, "median_s": 10.5, "p95_s": 19, "p95_method": "nearest rank"}


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_invalid_timing_cannot_enter_the_benchmark(bad):
    with pytest.raises(ValueError):
        latency([bad])


def test_grouping_missing_predictions_are_not_silently_removed():
    measured = binary_counts([True, False, True], [True, False, None])
    assert measured["n"] == 3 and measured["missing"] == 1 and measured["fn"] == 1
    assert measured["recall"] == 0.5


def test_numeric_gold_accepts_decimal_comma_without_matching_another_figure():
    assert key_present("5.4", "La magnitud es 5,4.")
    assert key_present("3,000", "El subsidio asciende a 3000 dólares.")
    assert key_present("32", "El subsidio es de 32 millones de dólares.")
    assert not key_present("4", "La magnitud es 5,4.")
    assert not key_present("151", "La caída es de 151,5 millones.")


def test_citation_coverage_checks_literal_passages_not_only_nonempty_urls():
    evidence = by_id(news("N-1", titulo="El Canal limitará a 32 los tránsitos diarios"))
    grounded = Answer(id_consulta="Q-1", consulta="¿Cuántos tránsitos?", estado="respondida", respuesta="Serán 32 tránsitos.",
                       citas=(Citation(id_evidencia="N-1", campo="titulo", pasaje="32 los tránsitos"),))
    assert score_answer(case(), grounded, evidence)["ok"]
    invented = grounded.model_copy(update={"citas": (Citation(id_evidencia="N-1", campo="titulo", pasaje="40 los tránsitos"),)})
    assert not score_answer(case(), invented, evidence)["citations_valid"]
    assert not score_answer(case(), invented, evidence)["ok"]


def human_review(subject_id, subject, **changes):
    return {"subject_id": subject_id, "subject_hash": subject_hash(subject), "reviewer": "Human test fixture",
            "reviewed_at": "2026-10-07T12:00:00Z", **changes}


def test_human_labels_only_replace_the_exact_reviewed_subject(tmp_path):
    original = {"id_noticia": "N-1", "titulo": "Noticia", "tema": "sin_tema"}
    path = tmp_path / "topics.jsonl"
    review = human_review("N-1", original, label="economia")
    path.write_text(json.dumps(review) + "\n", encoding="utf-8")
    labels, provenance = apply_human_labels([original], "topic", path)
    assert labels[0]["tema"] == "economia" and provenance["provenance"] == "human"
    labels, provenance = apply_human_labels([original | {"titulo": "Changed"}], "topic", path)
    assert labels[0]["tema"] == "sin_tema" and provenance["provenance"] != "human"
    assert provenance["failures"]


@pytest.mark.parametrize("reviewer", ["", "agent", "Claude", "Gemini", "ChatGPT"])
def test_agent_reviews_cannot_be_reported_as_human(reviewer):
    review = human_review("N-1", {}, reviewer=reviewer)
    with pytest.raises(ValueError, match="human"):
        verify_review(review, subject_hash({}))


def test_zero_human_reviews_cannot_pass_the_support_gate():
    metrics, packet = claim_evaluation([], {}, None)
    assert metrics["human_support"]["value"] is None
    assert not metrics["meets_human_target"]


def test_changed_evidence_invalidates_a_previous_human_claim_review(tmp_path):
    evidence = by_id(news("N-1", titulo="El Canal limitará a 32 los tránsitos"))
    claim = {"id_afirmacion": "A-1", "texto": "Serán 32 tránsitos.", "tipo": "hecho", "atribuida_a": None,
             "citas": [{"id_evidencia": "N-1", "campo": "titulo", "pasaje": "32 los tránsitos"}]}
    review = human_review("CASO-1/A-1", claim_subject("CASO-1", claim, evidence), verdict="supported")
    path = tmp_path / "claims.jsonl"
    path.write_text(json.dumps(review) + "\n", encoding="utf-8")
    cases = [{"id_caso": "CASO-1", "afirmaciones": [claim]}]
    measured, packet = claim_evaluation(cases, evidence, path)
    assert measured["reviewed_unique_claims"] == 1
    changed = by_id(news("N-1", titulo="El Canal limitará a 40 los tránsitos"))
    measured, packet = claim_evaluation(cases, changed, path)
    assert measured["reviewed_unique_claims"] == 0 and measured["review_errors"]


def test_frozen_development_split_is_40_and_jury_content_is_not_read():
    cases = load_cases(BENCHMARK, 40)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(cases) == 40 and all(item.id.startswith("D-") for item in cases)
    assert manifest["total"] == 60 and manifest["reserved"]["count"] == 20
    assert sha256(BENCHMARK) == manifest["development"]["sha256"]
    assert not list(BENCHMARK.parent.rglob("*reserved*.jsonl"))


def test_gold_answers_never_enter_generation_messages():
    evidence = by_id(news("N-1", titulo="El Canal limitará a 32 los tránsitos"))

    class Retriever:
        def search(self, query, k):
            return [("N-1", 0.9)]

    llm = FakeLLM([{"estado": "abstencion", "respuesta": None, "citas": [], "versiones": [],
                    "motivo_abstencion": "Sin respuesta", "faltante": "Fuentes adicionales"}])
    proposed = case(keys=["DO NOT SEND THIS GOLD LABEL TO THE MODEL"])
    answer_query(proposed.id, proposed.query, Retriever(), CosineGate(Retriever()), evidence, llm, "gemini-3.5-flash-lite")
    sent = json.dumps(llm.calls, ensure_ascii=False)
    assert proposed.keys[0] not in sent


def test_baseline_recall_and_latency_measure_the_same_queries():
    class Retriever:
        def __init__(self, identity):
            self.identity = identity
        def search(self, query, k):
            return [(self.identity, 1.0)]
    cases = [case("A", evidence_ids=["N-1"]), case("B", evidence_ids=["N-2"])]
    metrics, records = retrieval_benchmark(cases, {"bm25": Retriever("N-1"), "emb": Retriever("N-2")}, 2)
    assert len(records) == 8
    for method in metrics.values():
        assert method["micro_recall_at_8"] == {"numerator": 2, "denominator": 4, "value": 0.5}
        assert method["judged_queries"] == 2 and method["latency"]["n"] == 4


def test_tokens_separate_cached_usage_from_new_network_consumption():
    calls = [{"status": "ok", "cached": True, "prompt_tokens": 100, "completion_tokens": 20},
             {"status": "ok", "cached": False, "prompt_tokens": 200, "completion_tokens": 40},
             {"status": "LLMError"}]
    totals = token_totals(calls)
    assert totals["network_tokens"] == 240 and totals["prompt_tokens"] == 300
    assert totals["cache_hits"] == 1 and totals["network_calls"] == 1
    assert totals["failed_request_tokens"] is None and totals["cost"] is None


def test_vectors_from_another_corpus_cannot_be_silently_matched_by_position(tmp_path):
    path = tmp_path / "vectors.npy"
    np.save(path, np.array([[1.0, 0.0]]))
    (tmp_path / "manifest.json").write_text(json.dumps({"sha256_vectores": sha256(path), "ids": ["N-1"], "dimensiones": 2,
                                                     "nombre": MODEL_NAME, "revision": MODEL_REVISION}))
    evidence = by_id(news("N-2", titulo="Different corpus"))
    with pytest.raises(ValueError, match="exactly"):
        aligned_vectors(path, evidence)


def test_seeded_news_vectors_require_identical_text_and_queries_are_still_encoded():
    evidence = by_id(news("N-1", titulo="Frozen title"))
    seen = []

    class Embedder:
        def embed_documents(self, texts):
            seen.extend(texts)
            return np.tile([0.0, 1.0], (len(texts), 1))
        def embed_queries(self, texts):
            return np.tile([0.5, 0.5], (len(texts), 1))

    embedder = SeededEmbedder(Embedder(), ["N-1"], np.array([[1.0, 0.0]]), evidence)
    result = embedder.embed_documents(["Frozen title", "Changed title", "Official figure"])
    assert seen == ["Changed title", "Official figure"]
    assert np.array_equal(result, [[1, 0], [0, 1], [0, 1]])
    assert np.array_equal(embedder.embed_queries(["Frozen title"]), [[0.5, 0.5]])


def test_benchmark_expectations_are_provisional_until_a_human_accepts_the_current_corpus(tmp_path):
    cases = [case(evidence_ids=["N-1"])]
    evidence = by_id(news("N-1", titulo="El Canal anuncia mantenimiento"))
    status, packet = benchmark_reviews(cases, evidence, None)
    assert status["reviewed"] == 0 and not status["complete"]
    review = human_review("Q-1", packet[0]["subject"], verdict="accepted")
    path = tmp_path / "benchmark.jsonl"
    path.write_text(json.dumps(review), encoding="utf-8")
    status, _ = benchmark_reviews(cases, evidence, path)
    assert status["complete"]
    changed = by_id(news("N-1", titulo="Different source"))
    status, _ = benchmark_reviews(cases, changed, path)
    assert not status["complete"] and status["errors"]


def test_canary_leaks_in_missing_information_are_not_ignored():
    from whoami.evaluation.metrics import safety_check
    from whoami.generation.prompting import CANARY

    answer = Answer(id_consulta="Q-1", consulta="¿Qué falta?", estado="abstencion",
                    motivo_abstencion="Sin datos", faltante=f"La clave es {CANARY}")
    assert not safety_check("sin_canario", answer)


def test_an_unknown_safety_check_cannot_silently_pass():
    from whoami.evaluation.metrics import safety_check

    answer = Answer(id_consulta="Q-1", consulta="¿Qué falta?", estado="abstencion",
                    motivo_abstencion="Sin datos", faltante="La cifra")
    with pytest.raises(ValueError, match="Unknown"):
        safety_check("typo", answer)


def test_abstaining_on_an_answerable_contradiction_is_counted_as_wrong():
    cases = [case("A"), case("C", kind="contradiction", expected_states=["contradiccion"])]
    records = [{"id": item.id, "state": "abstencion", "ok": False, "safety": True, "citations_valid": False} for item in cases]
    result = answer_metrics(cases, records)
    assert result["wrong_abstentions"] == {"numerator": 2, "denominator": 2, "value": 1, "case_ids": ["A", "C"]}
    assert result["wrong_abstentions_supported_only"]["case_ids"] == ["A"]


def test_query_claim_coverage_cannot_be_inferred_from_a_shared_citation_list():
    cases = [case("A")]
    result = answer_metrics(cases, [{"id": "A", "state": "respondida", "ok": True, "safety": True, "citations_valid": True}])
    assert result["answer_citation_coverage"]["value"] == 1
    assert result["query_factual_claim_coverage"]["value"] is None


def test_reversing_citations_cannot_inflate_the_human_review_sample(tmp_path):
    evidence = by_id(news("N-1", titulo="El Canal limita tránsitos"), news("N-2", titulo="El Canal limita tránsitos"))
    citations = [{"id_evidencia": identity, "campo": "titulo", "pasaje": "limita tránsitos"} for identity in evidence]
    claims = [{"id_afirmacion": "A-1", "texto": "El Canal limita tránsitos.", "tipo": "hecho", "citas": citations},
              {"id_afirmacion": "A-2", "texto": "El Canal limita tránsitos.", "tipo": "hecho", "citas": citations[::-1]}]
    reviews = [human_review(f"CASO-1/{claim['id_afirmacion']}", claim_subject("CASO-1", claim, evidence), verdict="supported") for claim in claims]
    path = tmp_path / "claims.jsonl"
    path.write_text("\n".join(json.dumps(review) for review in reviews), encoding="utf-8")
    result, _ = claim_evaluation([{"id_caso": "CASO-1", "afirmaciones": claims}], evidence, path)
    assert result["reviewed_unique_claims"] == 1
    assert result["review_errors"]


def test_replay_into_the_original_directory_is_rejected_before_any_writes(tmp_path):
    from argparse import Namespace

    artifact = tmp_path / "benchmark_review_packet.jsonl"
    artifact.write_bytes(b"original archived packet")
    args = Namespace(repeats=1, generate_cases=0, output=tmp_path, reuse_generation=tmp_path)
    with pytest.raises(ValueError, match="differ"):
        evaluate(args)
    assert artifact.read_bytes() == b"original archived packet"


def test_replay_cannot_use_original_timings_against_changed_synthetic_sources():
    first = by_id(news("N-1", titulo="Real source"), news("N-syn1", titulo="Original synthetic source"))
    changed = by_id(news("N-1", titulo="Real source"), news("N-syn1", titulo="Changed synthetic source"))
    fingerprint = lambda records: subject_hash({identity: item.model_dump(mode="json") for identity, item in records.items()})
    saved = {"evidence_sha256": "unchanged-real-file", "evaluation_corpus_sha256": fingerprint(first)}
    validate_saved_inputs(saved, saved)
    with pytest.raises(ValueError, match="evaluation_corpus"):
        validate_saved_inputs(saved, {"evidence_sha256": "unchanged-real-file", "evaluation_corpus_sha256": fingerprint(changed)})


def test_g7_t01_invalid_dates_and_nulls_do_not_block_valid_rows(tmp_path, monkeypatch):
    from whoami.ingest.news import build
    from whoami.ingest.news.channels import rss
    from whoami.ingest.news.sources import SOURCES, Channel
    from whoami.ingest.raw import RawStore

    source = next(item for item in SOURCES if item.key == "tvn")
    raw = RawStore(Path(__file__).parent / "fixtures/evaluation/news")
    parsed = list(rss.parse(source, raw))
    assert len(parsed) == 4 and sum(item.published_at is None for item in parsed) == 2
    monkeypatch.setattr(build, "SOURCES", (source,))
    monkeypatch.setattr(build.channels, "parse", lambda selected, feed: parsed if feed.channel == Channel.RSS else [])
    monkeypatch.setattr(build, "PROCESSED", tmp_path)
    for name, filename in (("NEWS_CSV", "noticias.csv"), ("EXCLUDED_NEWS_CSV", "excluidas.csv"),
                           ("NEWS_QUALITY_JSON", "quality.json"), ("SOURCES_JSON", "sources.json")):
        monkeypatch.setattr(build, name, tmp_path / filename)
    report = build.build()
    rows = list(csv.DictReader((tmp_path / "noticias.csv").open(encoding="utf-8", newline="")))
    excluded = list(csv.DictReader((tmp_path / "excluidas.csv").open(encoding="utf-8", newline="")))
    assert len(rows) == 2 and len(excluded) == 2
    assert {row["motivo"] for row in excluded} == {"sin_fecha"}
    assert next(row for row in rows if row["titulo"] == "Descripción nula")["descripcion"] == ""
    assert report["incluidas"] == 2 and report["excluidas_por_motivo"]["sin_fecha"] == 2
