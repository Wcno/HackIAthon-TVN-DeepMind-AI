"""The comparison only scores complete human judgments against a frozen input pool."""

from fastapi.testclient import TestClient
import pytest

from whoami.model_comparison import build_snapshot, create_review_app, score, ReviewStore


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
