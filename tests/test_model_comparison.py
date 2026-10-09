"""The comparison only scores complete human judgments against a frozen input pool."""

from fastapi.testclient import TestClient
import pytest

from whoami.model_comparison import build_snapshot, create_review_app, score, ReviewStore


def agent_reviews(frozen):
    return [{"snapshot": frozen["fingerprint"], "reviewer_kind": "agent", "actor": "Fixture AI reviewer",
             "item": item["id"], "grade": "same_event" if item["kind"] == "pair" else "2",
             "reason": "Fixture-only explicit grade"} for item in frozen["items"]]


def test_agent_score_never_claims_human_completion_or_touches_human_data(tmp_path):
    from whoami.model_comparison import score_agent_reviews
    frozen = snapshot()
    humans = ReviewStore(tmp_path / "human.sqlite3", frozen)
    result = score_agent_reviews(frozen, agent_reviews(frozen))
    assert result["status"] == "agent_review_complete"
    assert result["reviewer_kind"] == "agent"
    assert result["retrieval"]["q4"]["pooled_recall_at_5"] == pytest.approx(5 / 6)
    assert humans.labels() == {}
    assert score(frozen, humans)["status"] == "awaiting_human_review"


@pytest.mark.parametrize("field,value", [("reviewer_kind", "human"), ("snapshot", "wrong"),
                                       ("grade", "invalid"), ("reason", " "), ("actor", " ")])
def test_agent_score_rejects_wrong_origin_identity_and_incomplete_evidence(field, value):
    from whoami.model_comparison import score_agent_reviews
    frozen = snapshot()
    reviews = agent_reviews(frozen)
    reviews[0][field] = value
    with pytest.raises(ValueError):
        score_agent_reviews(frozen, reviews)
    with pytest.raises(ValueError, match="repeated"):
        score_agent_reviews(frozen, [agent_reviews(frozen)[0]] * 2)


def test_agent_unknown_is_assessed_but_never_used_as_a_negative():
    from whoami.model_comparison import score_agent_reviews
    frozen = snapshot()
    reviews = agent_reviews(frozen)
    pair = next(review for review in reviews if review["item"] == "P1")
    pair["grade"] = "unknown"
    result = score_agent_reviews(frozen, reviews)
    assert result["status"] == "agent_review_complete"
    assert result["metrics_complete"] is False
    assert result["unknown"] == 1
    assert result["grouping"]["q4"]["reviewed_pairs"] == 0
    assert result["grouping"]["q4"]["f1"] is None


def test_agent_results_fold_optional_human_forms_and_have_a_separate_page(tmp_path):
    from whoami.model_comparison import score_agent_reviews
    frozen = snapshot()
    report = score_agent_reviews(frozen, agent_reviews(frozen))
    database = tmp_path / "human.sqlite3"
    client = TestClient(create_review_app(frozen, database, agent_report=report))
    page = client.get("/")
    assert "Evaluación del agente completada: 7 / 7" in page.text
    assert '<details><summary>Revisión humana opcional</summary>' in page.text
    results = client.get("/agent-results")
    assert results.status_code == 200
    assert "fp32" in results.text
    assert "No se presentan como revisión humana" in results.text
    assert ReviewStore(database, frozen).labels() == {}
    report["reviewer_kind"] = "human"
    with pytest.raises(ValueError, match="agent origin"):
        create_review_app(frozen, database, agent_report=report)


def snapshot():
    rows = [{"id_noticia": str(i), "titulo": f"News {i}", "descripcion": "", "url": "https://example.com",
             "fecha_publicacion": "2026-10-01T12:00:00Z", "medio": "Test"} for i in range(6)]
    candidates = {"q4": {"rankings": {"Q1": [str(i) for i in range(5)]}, "pair_predictions": {"P1": True}},
                  "fp32": {"rankings": {"Q1": [str(i) for i in range(1, 6)]}, "pair_predictions": {"P1": False}}}
    return build_snapshot(rows, [{"qid": "Q1", "consulta": "News"}], candidates,
                          [{"id": "P1", "id_a": "0", "id_b": "1"}])


def test_no_results_or_model_change_without_human_labels(tmp_path):
    frozen = snapshot()
    result = score(frozen, ReviewStore(tmp_path / "human.sqlite3", frozen))
    assert result["status"] == "awaiting_human_review"
    assert result["decision"] == "keep_q4"
    assert result["retrieval"]["q4"]["eligible_queries"] == 0
    assert result["grouping"]["q4"]["f1"] is None


def test_actual_pooled_recall_and_grouping_use_human_grades(tmp_path):
    frozen = snapshot()
    store = ReviewStore(tmp_path / "human.sqlite3", frozen)
    for item in frozen["items"]:
        grade = "same_event" if item["kind"] == "pair" else "2"
        store.save(item["id"], grade, "Fixture reviewer")
    result = score(frozen, store)
    assert result["status"] == "human_review_complete"
    assert result["retrieval"]["q4"]["pooled_recall_at_5"] == pytest.approx(5 / 6)
    assert result["retrieval"]["q4"]["precision_at_5"] == 1
    assert result["grouping"]["q4"]["f1"] == 1
    assert result["grouping"]["fp32"]["f1"] == 0
    assert result["decision"] == "keep_q4"  # changing production always remains a separate decision


def test_unknowns_and_partial_queries_do_not_become_irrelevant(tmp_path):
    frozen = snapshot()
    store = ReviewStore(tmp_path / "human.sqlite3", frozen)
    store.save(frozen["items"][0]["id"], "unknown", "Reviewer")
    assert score(frozen, store)["retrieval"]["q4"]["eligible_queries"] == 0
    assert score(frozen, store)["status"] == "awaiting_human_review"


def test_rejects_stale_database_and_wrong_document_ids(tmp_path):
    frozen = snapshot()
    ReviewStore(tmp_path / "human.sqlite3", frozen)
    different = snapshot()
    different["fingerprint"] = "different"
    with pytest.raises(ValueError, match="snapshot"):
        ReviewStore(tmp_path / "human.sqlite3", different)
    with pytest.raises(ValueError, match="document"):
        build_snapshot([], [{"qid": "Q", "consulta": "q"}],
                       {"q4": {"rankings": {"Q": ["missing"]}, "pair_predictions": {}}}, [])


def test_blind_review_validates_actor_csrf_and_persists(tmp_path):
    frozen = snapshot()
    database = tmp_path / "human.sqlite3"
    app = create_review_app(frozen, database)
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert "fp32" not in page.text and "q4" not in page.text
    assert "01/10/2026 07:00 (Panamá)" in page.text
    item = frozen["items"][0]
    grade = "same_event" if item["kind"] == "pair" else "2"
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    assert client.post("/label", data={"item": item["id"], "grade": grade, "actor": "Ana"}).status_code == 403
    assert client.post("/label", data={"item": item["id"], "grade": grade, "actor": " ", "csrf": csrf}).status_code == 422
    response = client.post("/label", data={"item": item["id"], "grade": grade, "actor": "Ana", "csrf": csrf})
    assert response.status_code == 200
    assert ReviewStore(database, frozen).labels()[item["id"]]["actor"] == "Ana"
    assert TestClient(create_review_app(frozen, database)).get("/").status_code == 200


def test_candidate_resume_rejects_changed_model_files_and_other_builds():
    from whoami.comparison_prepare import validate_cached_report
    from whoami.embeddings import MODEL_REPO, MODEL_REVISION
    context = {"full_rows": "fixture"}
    expected = {"weights": "pinned-hash"}
    cached = {"context": context, "provenance": {"files": {"weights": "different-hash"}, "model": "fp32",
                                                  "revision": MODEL_REVISION, "repository": MODEL_REPO}}
    with pytest.raises(ValueError, match="model identity"):
        validate_cached_report(cached, "fp32", context, expected)
    cached["provenance"]["files"] = expected
    cached["provenance"]["model"] = "q4"
    with pytest.raises(ValueError, match="model identity"):
        validate_cached_report(cached, "fp32", context, expected)


@pytest.mark.parametrize("field,new_value", [("fecha_publicacion", "2026-10-05T12:00:00Z"),
                                           ("medio", "Changed outlet"), ("fecha_deteccion", "2026-10-07T12:00:00Z")])
def test_resume_identity_includes_dates_and_lexical_metadata(monkeypatch, field, new_value):
    from whoami import comparison_prepare as prepare
    rows = list(snapshot()["documents"].values())
    monkeypatch.setattr(prepare, "load_news_rows", lambda: rows)
    previous = prepare.public_inputs()[3]
    rows[0][field] = new_value
    changed = prepare.public_inputs()[3]
    assert previous["corpus"] == changed["corpus"]
    assert previous["full_rows"] != changed["full_rows"]
    with pytest.raises(ValueError, match="different corpus"):
        prepare.validate_cached_report({"context": previous, "provenance": {}}, "q4", changed, {})
