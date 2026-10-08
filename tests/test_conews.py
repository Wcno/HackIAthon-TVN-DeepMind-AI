"""G6: Co-News, the draft assistant, rewrites a chosen field or the whole draft on the journalist's request.

It keeps the assistant's rules: cited, figures checked, and nothing changes until the journalist applies a proposal.
"""

import json

import httpx
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings

CITATION = {"id_evidencia": "N-2cf673d2b74a", "campo": "titulo",
            "pasaje": "El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún"}
TEXT_FIELDS = ["titulo", "brief", "enfoque_interes_publico", "guion", "copy_digital"]


def suggestion(field, text):
    return {"kind": "suggestion", "text": "Más fácil de leer al aire.", "field": field, "options": [text],
            "citations": [CITATION], "missing": None}


def client_with(tmp_path, reply, seen=None):
    def provider(request):
        payload = json.loads(request.content)
        if seen is not None:
            seen.append(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})
    settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret")
    return TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider)))


def rewrite(client, question, field=None):
    record = client.get("/api/cases/CASO-001/draft").json()
    body = {"question": question, "action": "rewrite", "draft": record["draft"]}
    if field:
        body["field"] = field
    return client.post("/api/cases/CASO-001/assistant", json=body), record


def test_a_field_request_is_constrained_to_that_field_and_carries_the_instruction(tmp_path):
    seen = []
    text = "El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún."
    with client_with(tmp_path, suggestion("guion", text), seen) as client:
        response, before = rewrite(client, "Hazlo más fácil de leer al aire", "guion")
        assert response.status_code == 200
        assert response.json()["field"] == "guion" and response.json()["options"] == [text]
        schema = seen[0]["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["kind"]["enum"] == ["suggestion", "abstention"]
        assert schema["properties"]["field"]["enum"] == ["guion", None]
        sent = json.loads(seen[0]["messages"][1]["content"])
        assert sent["question"] == "Hazlo más fácil de leer al aire" and sent["field"] == "guion"
        assert client.get("/api/cases/CASO-001/draft").json() == before  # a proposal never saves


def test_a_rewrite_is_grounded_on_the_case_sources_not_on_a_corpus_search_of_the_request(tmp_path):
    # "45-60 segundos" would otherwise pull earthquakes and indicators that merely contain those numbers.
    seen = []
    with client_with(tmp_path, suggestion("guion", "El Canal reduce a 32 los tránsitos diarios."), seen) as client:
        rewrite(client, "Ajústalo a 45-60 segundos", "guion")
        case = client.app.state.repository.case("CASO-001")
        sent = json.loads(seen[0]["messages"][1]["content"])["sources"]
        assert set(sent) <= set(client.app.state.assistant.sources(case))


def test_the_whole_draft_lets_co_news_choose_which_text_field_to_improve(tmp_path):
    seen = []
    with client_with(tmp_path, suggestion("brief", "El Canal reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún."), seen) as client:
        response, _ = rewrite(client, "Mejora el borrador para televisión")
        assert response.status_code == 200 and response.json()["field"] == "brief"
        assert seen[0]["response_format"]["json_schema"]["schema"]["properties"]["field"]["enum"] == [*TEXT_FIELDS, None]


def test_a_proposal_for_another_field_than_the_one_asked_is_refused(tmp_path):
    with client_with(tmp_path, suggestion("titulo", "El Canal reduce a 32 los tránsitos diarios por la sequía")) as client:
        response, _ = rewrite(client, "Hazlo más corto", "copy_digital")
        assert response.status_code == 503


def test_only_text_fields_can_be_rewritten(tmp_path):
    with client_with(tmp_path, suggestion("guion", "x")) as client:
        response, _ = rewrite(client, "Añade una pregunta", "preguntas")
        assert response.status_code == 422


def test_the_draft_tab_presents_co_news_with_a_scope_and_a_button_per_field(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "db.sqlite3"))) as client:
        html = client.get("/cases/CASO-001/draft").text
        assert ">Co-News<" in html and 'id="cn-scope"' in html
        assert '<option value="todo">Todo el borrador</option>' in html
        for field in TEXT_FIELDS:
            assert f'<option value="{field}">' in html and f'data-cn-field="{field}"' in html
        assert 'data-action="rewrite"' in html
