"""Local generation through the same public editorial HTTP interface."""

import json

import httpx
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings


def test_fresh_question_is_grounded_offline_without_a_cloud_key(tmp_path):
    requests = []
    reply = {"estado": "respondida", "respuesta": "La Autoridad del Canal limitará a 32 los tránsitos diarios.",
             "citas": [{"id_evidencia": "N-2cf673d2b74a", "campo": "descripcion",
                        "pasaje": "limitará a 32 los tránsitos diarios"}],
             "motivo_abstencion": None, "faltante": None, "versiones": []}

    def provider(request):
        assert request.url.host == "127.0.0.1"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}]})

    settings = Settings(database=tmp_path / "editorial.sqlite3", offline=True, generation_provider="qvac")
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider))) as client:
        response = client.get("/queries", params={"q": "¿A cuántos tránsitos diarios se limitará el Canal en octubre?"})
        assert response.status_code == 200
        assert "Respuesta con evidencia" in response.text and "32 los tránsitos" in response.text
        assert "/evidence/N-2cf673d2b74a" in response.text
    assert len(requests) == 1
    assert requests[0]["model"] == "g10-generator"
    assert requests[0]["reasoning_budget"] is False


def test_local_case_generation_is_enabled_and_survives_restart(tmp_path):
    purposes = []
    replies = {"afirmaciones": {"afirmaciones": [{
        "texto": "El Servicio Geológico de EE. UU. reportó el sismo frente a Burica.", "tipo": "hecho", "atribuida_a": None,
        "citas": [{"id_evidencia": "N-5a85a8d35030", "campo": "descripcion",
                   "pasaje": "El Servicio Geológico de EE. UU. reportó el sismo frente a las costas de Burica."}]}]},
        "paquete": {"titulo": ["A-1"], "brief": ["A-1"], "guion": ["A-1"], "copy_digital": ["A-1"],
                    "enfoque": "impacto", "preguntas": ["fuentes", "vacios", "actualizaciones"]}}

    def provider(request):
        purpose = json.loads(request.content)["response_format"]["json_schema"]["name"]
        purposes.append(purpose)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(replies[purpose])}}]})

    settings = Settings(database=tmp_path / "editorial.sqlite3", offline=True, generation_provider="qvac")
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider))) as client:
        html = client.get("/groups/G-006").text
        assert "disabled" not in html.split("Generar ficha")[0].rsplit("<button", 1)[1]
        response = client.post("/groups/G-006/case-file", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/cases/CASO-006"
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider))) as client:
        response = client.get("/cases/CASO-006/draft")
        assert response.status_code == 200 and "Burica" in response.text
        assert "QVAC" in response.text
    assert purposes == ["afirmaciones", "paquete"]


def test_local_assistant_cites_sources_and_never_changes_the_draft_itself(tmp_path):
    reply = {"kind": "suggestion", "text": "Un titular más directo.", "field": "titulo",
             "options": ["El Canal limita a 32 los tránsitos diarios por la sequía"], "missing": None,
             "citations": [{"id_evidencia": "N-2cf673d2b74a", "campo": "titulo",
                            "pasaje": "El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún"}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps(reply)}}]}))
    settings = Settings(database=tmp_path / "db.sqlite3", generation_provider="qvac")
    with TestClient(create_app(settings, gemini_transport=transport)) as client:
        before = client.get("/api/cases/CASO-001/draft").json()
        result = client.post("/api/cases/CASO-001/assistant", json={
            "question": "Propón un titular alternativo", "action": "headlines", "draft": before["draft"]})
        assert result.status_code == 200 and result.json()["kind"] == "suggestion"
        assert result.json()["origin"] == "qvac"
        assert client.get("/api/cases/CASO-001/draft").json() == before
