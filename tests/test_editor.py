"""The editor is tested through HTTP, with a real temporary SQLite database."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings


def test_saved_draft_and_added_questions_survive_restart(tmp_path):
    settings = Settings(database=tmp_path / "editor.sqlite3")
    with TestClient(create_app(settings)) as client:
        initial = client.get("/api/cases/CASO-001/draft")
        assert initial.status_code == 200
        record = initial.json()
        record["draft"]["titulo"] = "Un título editado por la redacción"
        record["draft"]["preguntas"].append("¿Cuándo se revisará la medida?")
        response = client.put("/api/cases/CASO-001/draft", json={
            "draft": record["draft"], "source_ids": record["source_ids"],
            "expected_version": record["version"],
        })
        assert response.status_code == 200
    with TestClient(create_app(settings)) as client:
        saved = client.get("/api/cases/CASO-001/draft").json()
        assert saved["draft"]["titulo"] == "Un título editado por la redacción"
        assert saved["draft"]["preguntas"][-1] == "¿Cuándo se revisará la medida?"
        assert len(saved["draft"]["preguntas"]) == 4


def test_edits_revoke_approval_and_stale_saves_do_not_overwrite(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "db.sqlite3"))) as client:
        for state in ("en_revision", "aprobado_como_borrador"):
            version = client.get("/api/cases/CASO-004/draft").json()["version"]
            assert client.post("/cases/CASO-004/review", data={"state": state, "actor": "Editor", "expected_version": version}).status_code == 200
        record = client.get("/api/cases/CASO-004/draft").json()
        assert record["review_state"] == "aprobado_como_borrador"
        payload = {"draft": record["draft"], "source_ids": record["source_ids"], "expected_version": record["version"]}
        payload["draft"]["preguntas"] = []
        saved = client.put("/api/cases/CASO-004/draft", json=payload)
        assert saved.status_code == 200
        assert saved.json()["review_state"] == "nuevo"
        payload["draft"]["titulo"] = "Edición obsoleta"
        assert client.put("/api/cases/CASO-004/draft", json=payload).status_code == 409
        current = client.get("/api/cases/CASO-004/draft").json()
        assert current["draft"]["titulo"] != "Edición obsoleta"
        assert current["draft"]["preguntas"] == []


def test_assistant_finds_corpus_articles_and_added_sources_persist(tmp_path):
    settings = Settings(database=tmp_path / "db.sqlite3")
    with TestClient(create_app(settings)) as client:
        record = client.get("/api/cases/CASO-002/draft").json()
        response = client.post("/api/cases/CASO-002/assistant", json={
            "question": "Busca noticias sobre el Canal", "action": "articles", "draft": record["draft"],
        })
        assert response.status_code == 200
        answer = response.json()
        assert answer["kind"] == "articles"
        assert any("Canal" in article["titulo"] for article in answer["articles"])
        source = answer["articles"][0]
        assert source["id_evidencia"] not in record["source_ids"]
        record["source_ids"].append(source["id_evidencia"])
        saved = client.put("/api/cases/CASO-002/draft", json={
            "draft": record["draft"], "source_ids": record["source_ids"], "expected_version": record["version"],
        })
        assert saved.status_code == 200
        assert source["id_evidencia"] in client.get("/api/cases/CASO-002/draft").json()["source_ids"]
        source_response = client.get(f"/api/evidence/{source['id_evidencia']}")
        assert source_response.status_code == 200
        assert source_response.json()["titulo"] == source["titulo"]


def test_unsaved_selected_sources_are_available_to_the_assistant_without_saving(tmp_path):
    source_id = "N-2cf673d2b74a"
    def provider(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert source_id in data["sources"]
        reply = {"kind": "answer", "text": "La fuente informa sobre el Canal.",
                 "citations": [{"id_evidencia": source_id, "campo": "titulo", "pasaje": "Canal"}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})
    settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="fixture")
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider))) as client:
        before = client.get("/api/cases/CASO-002/draft").json()
        assert source_id not in before["source_ids"]
        response = client.post("/api/cases/CASO-002/assistant", json={
            "question": "Resume la fuente que seleccioné", "draft": before["draft"], "source_ids": [source_id],
        })
        assert response.status_code == 200
        assert response.json()["citations"][0]["id_evidencia"] == source_id
        assert client.get("/api/cases/CASO-002/draft").json() == before


def test_headline_requests_constrain_the_provider_to_suggestions_or_abstention(tmp_path):
    def provider(request):
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        schema = payload["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["kind"]["enum"] == ["suggestion", "abstention"]
        assert payload["max_tokens"] <= 1200
        reply = {"kind": "suggestion", "text": "Un titular más directo.", "field": "titulo",
                 "options": ["El Canal reduce a 32 los tránsitos diarios por la sequía"],
                 "citations": [{"id_evidencia": "N-2cf673d2b74a", "campo": "titulo", "pasaje": "32"}], "missing": None}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})
    settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret")
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider))) as client:
        record = client.get("/api/cases/CASO-001/draft").json()
        response = client.post("/api/cases/CASO-001/assistant", json={
            "question": "Propón tres titulares alternativos", "action": "headlines", "draft": record["draft"],
        })
        assert response.status_code == 200
        assert response.json()["kind"] == "suggestion"


def test_gemini_suggests_a_cited_title_without_overwriting_the_draft(tmp_path):
    reply = {"kind": "suggestion", "text": "Un titular más directo.", "field": "titulo",
             "options": ["El Canal reduce a 32 los tránsitos diarios por la sequía"],
             "citations": [{"id_evidencia": "N-2cf673d2b74a", "campo": "titulo",
                            "pasaje": "El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún"}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]}))
    settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret")
    with TestClient(create_app(settings, gemini_transport=transport)) as client:
        before = client.get("/api/cases/CASO-001/draft").json()
        response = client.post("/api/cases/CASO-001/assistant", json={
            "question": "Propón un titular alternativo", "action": "headlines", "draft": before["draft"],
        })
        assert response.status_code == 200
        assert response.json()["kind"] == "suggestion"
        assert response.json()["options"] == ["El Canal reduce a 32 los tránsitos diarios por la sequía"]
        assert client.get("/api/cases/CASO-001/draft").json() == before


@pytest.mark.parametrize("invalid", ["invented-citation", "unsupported-number", "provider-failure"])
def test_invalid_provider_results_are_controlled_and_never_saved(tmp_path, invalid):
    def provider(request):
        if invalid == "provider-failure":
            return httpx.Response(401, text="test-secret")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "kind": "answer", "text": "El Canal tendrá 9999 tránsitos diarios." if invalid == "unsupported-number" else "Una respuesta.",
            "citations": [{"id_evidencia": "N-2cf673d2b74a", "campo": "titulo",
                           "pasaje": "pasaje inventado" if invalid == "invented-citation" else "32"}],
        })}}]})
    settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret")
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider))) as client:
        before = client.get("/api/cases/CASO-001/draft").json()
        response = client.post("/api/cases/CASO-001/assistant", json={
            "question": "¿Cuántos tránsitos tendrá el Canal?", "draft": before["draft"],
        })
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/json")
        assert "test-secret" not in response.text
        assert response.json()["message"]
        assert client.get("/api/cases/CASO-001/draft").json() == before


def test_offline_assistant_abstains_without_network_and_answers_saved_questions(tmp_path):
    def no_network(request):
        pytest.fail("Offline assistant attempted a network request")
    settings = Settings(database=tmp_path / "db.sqlite3", offline=True)
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(no_network))) as client:
        draft = client.get("/api/cases/CASO-001/draft").json()["draft"]
        response = client.post("/api/cases/CASO-001/assistant", json={"question": "¿Qué pasará mañana?", "draft": draft})
        assert response.status_code == 200
        assert response.json()["kind"] == "abstention"
        assert "Sin conexión" in response.json()["text"]
        useful = client.post("/api/cases/CASO-001/assistant", json={"question": "¿Cuántos tránsitos diarios limitará el Canal?", "draft": draft})
        assert useful.status_code == 200
        assert useful.json()["kind"] == "answer"
        assert useful.json()["citations"]


def test_draft_screen_exposes_the_editor_assistant_and_local_assets(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "db.sqlite3"))) as client:
        response = client.get("/cases/CASO-001/draft")
        assert response.status_code == 200
        html = response.text
        assert 'data-editor="CASO-001"' in html
        assert 'data-key="titulo"' in html
        assert "Añadir pregunta" in html and "Quitar pregunta" in html
        assert "Asistente del borrador" in html
        assert "/static/editor.js" in html
        assert "https://cdn" not in html
        assert "Cifra sin respaldo" not in html
        assert client.get("/static/editor.js").status_code == 200


def test_environment_defaults_use_real_data_and_online_only_with_a_key(tmp_path, monkeypatch):
    from whoami.contracts import OUTPUTS, PROCESSED

    monkeypatch.setenv("WHOAMI_ENV_FILE", str(tmp_path / "missing.env"))
    for name in ("WHOAMI_DEMO", "WHOAMI_OFFLINE", "WHOAMI_DATA_DIRECTORY", "WHOAMI_OUTPUT_DIRECTORY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WHOAMI_DATABASE", str(tmp_path / "real.sqlite3"))
    settings = Settings.from_environment()
    assert not settings.demo
    assert settings.data_directory == PROCESSED
    assert settings.output_directory == OUTPUTS
    assert settings.offline
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    assert not Settings.from_environment().offline
    monkeypatch.setenv("WHOAMI_OFFLINE", "1")
    assert Settings.from_environment().offline
    monkeypatch.setenv("WHOAMI_DEMO", "1")
    assert Settings.from_environment().demo


def test_backend_loads_existing_env_file_without_overriding_explicit_flags(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=fixture-key\nWHOAMI_DEMO=0\n", encoding="utf-8")
    monkeypatch.setenv("WHOAMI_ENV_FILE", str(env_file))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("WHOAMI_OFFLINE", raising=False)
    settings = Settings.from_environment()
    assert settings.gemini_api_key == "fixture-key"
    assert not settings.offline
    monkeypatch.setenv("WHOAMI_OFFLINE", "1")
    assert Settings.from_environment().offline
