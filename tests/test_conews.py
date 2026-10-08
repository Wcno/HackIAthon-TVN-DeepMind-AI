"""G6: Co-News, the draft assistant, rewrites a chosen field or the whole draft on the journalist's request.

It keeps the assistant's rules: cited, figures checked, and nothing changes until the journalist applies a proposal.
"""

import json

import httpx
import pytest
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


def client_with_replies(tmp_path, replies, seen):
    """A provider that answers with each reply in turn and then repeats the last one."""
    queue = list(replies)

    def provider(request):
        seen.append(json.loads(request.content))
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})
    settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret")
    return TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider)))


def cached_replies(client):
    with client.app.state.repository.connection() as connection:
        return connection.execute("SELECT count(*) FROM generation_cache").fetchone()[0]


UNBACKED = suggestion("titulo", "Canal limita a 32 tránsitos y 1.000.000 de dólares")
GOOD = suggestion("titulo", "El Canal reduce a 32 los tránsitos diarios")
WRONG_FIELD = suggestion("guion", "El Canal reduce a 32 los tránsitos diarios")


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


def test_a_proposal_for_another_field_than_the_one_asked_ends_in_a_friendly_abstention_not_an_error(tmp_path):
    seen = []
    with client_with_replies(tmp_path, [suggestion("titulo", "El Canal reduce a 32 los tránsitos diarios por la sequía")], seen) as client:
        response, _ = rewrite(client, "Hazlo más corto", "copy_digital")
        assert response.status_code == 200 and len(seen) == 3
        assert response.json()["kind"] == "abstention" and "No pude generar una versión válida" in response.json()["text"]
        assert cached_replies(client) == 0


def test_a_rejected_reply_is_retried_with_the_failure_as_feedback_and_without_resending_the_evidence(tmp_path):
    seen = []
    with client_with_replies(tmp_path, [UNBACKED, GOOD], seen) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.status_code == 200 and response.json()["options"] == GOOD["options"]
        assert "warnings" not in response.json() or response.json()["warnings"] == []
        assert len(seen) == 2 and seen[1]["messages"][:2] == seen[0]["messages"]
        assert [m["role"] for m in seen[1]["messages"]] == ["system", "user", "assistant", "user"]
        assert json.loads(seen[1]["messages"][2]["content"]) == UNBACKED
        assert "1.000.000" in seen[1]["messages"][3]["content"]
        assert cached_replies(client) == 1  # only the valid reply


def test_three_unbacked_replies_are_returned_with_a_warning_per_issue_and_never_cached(tmp_path):
    seen = []
    with client_with_replies(tmp_path, [UNBACKED], seen) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.status_code == 200 and len(seen) == 3
        assert response.json()["kind"] == "suggestion" and response.json()["options"] == UNBACKED["options"]
        assert response.json()["warnings"] == ["Cifra sin respaldo: 1.000.000"]
        assert response.json()["option_warnings"] == [["Cifra sin respaldo: 1.000.000"]]
        assert cached_replies(client) == 0


def test_a_scale_word_without_a_number_is_not_an_unbacked_figure(tmp_path):
    seen = []
    with client_with_replies(tmp_path, [suggestion("titulo", "Millones en juego por 32 tránsitos diarios")], seen) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.status_code == 200 and len(seen) == 1 and not response.json().get("warnings")


def test_a_quote_that_differs_only_in_case_and_accents_is_repaired_before_it_is_checked(tmp_path):
    inexact = suggestion("titulo", "El Canal reduce a 32 los tránsitos diarios") | {
        "citations": [CITATION | {"pasaje": CITATION["pasaje"].upper().replace("Á", "A")}]}
    seen = []
    with client_with_replies(tmp_path, [inexact], seen) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.status_code == 200 and len(seen) == 1
        assert response.json()["citations"] == [CITATION] and not response.json().get("warnings")


def test_every_rejection_logs_which_check_failed(tmp_path, caplog):
    with caplog.at_level("WARNING"), client_with_replies(tmp_path, [UNBACKED, WRONG_FIELD, GOOD], []) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
    assert response.status_code == 200
    rejections = [record.getMessage() for record in caplog.records if "rejected" in record.getMessage()]
    assert len(rejections) == 2 and "unsupported_figures" in rejections[0] and "wrong_field" in rejections[1]


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


def test_a_warning_belongs_to_the_option_it_concerns(tmp_path):
    two = suggestion("titulo", "El Canal reduce a 32 los tránsitos diarios") | {
        "options": ["El Canal reduce a 32 los tránsitos diarios", UNBACKED["options"][0]]}
    with client_with_replies(tmp_path, [two], []) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.json()["option_warnings"] == [[], ["Cifra sin respaldo: 1.000.000"]]


def current_text(tmp_path, field):
    with TestClient(create_app(Settings(database=tmp_path / "current.sqlite3"))) as client:
        return client.get("/api/cases/CASO-001/draft").json()["draft"][field]


def test_an_option_identical_to_the_current_text_is_rejected_and_retried_with_feedback(tmp_path):
    seen = []
    same = suggestion("titulo", current_text(tmp_path, "titulo"))
    with client_with_replies(tmp_path, [same, GOOD], seen) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.json()["options"] == GOOD["options"] and len(seen) == 2
        assert "idéntica" in seen[1]["messages"][3]["content"]


def test_a_script_outside_the_broadcast_range_is_flagged_after_the_retries(tmp_path):
    seen = []
    short = suggestion("guion", "El Canal reduce a 32 los tránsitos diarios.")
    with client_with_replies(tmp_path, [short], seen) as client:
        response, _ = rewrite(client, "Ajústalo a 45-60 segundos", "guion")
        assert len(seen) == 3 and "segundos" in seen[1]["messages"][3]["content"]
        assert response.json()["option_warnings"] == [["Fuera del rango de 45-60 segundos: unos 3 s"]]


def test_a_script_inside_the_broadcast_range_has_no_warning(tmp_path):
    seen = []
    text = " ".join(["El Canal reduce a 32 los tránsitos diarios."] * 17)
    with client_with_replies(tmp_path, [suggestion("guion", text)], seen) as client:
        response, _ = rewrite(client, "Ajústalo a 45-60 segundos", "guion")
        assert len(seen) == 1 and not any(response.json()["option_warnings"])


def test_offline_edit_requests_abstain_naming_the_action(tmp_path):
    def no_network(request):
        pytest.fail("Offline Co-News attempted a network request")
    settings = Settings(database=tmp_path / "db.sqlite3", offline=True)
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(no_network))) as client:
        response, _ = rewrite(client, "Haz el título más llamativo", "titulo")
        assert response.json()["kind"] == "abstention"
        assert "Haz el título más llamativo" in response.json()["text"] and "Sin conexión:" in response.json()["text"]


def test_no_recorded_contradictions_is_an_answer_not_an_abstention(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "db.sqlite3", offline=True))) as client:
        record = client.get("/api/cases/CASO-001/draft").json()
        if client.app.state.repository.case("CASO-001")["contradicciones"]:
            pytest.skip("fixture case has contradictions")
        response = client.post("/api/cases/CASO-001/assistant", json={"action": "contradictions", "question": "¿Hay contradicciones?", "draft": record["draft"]})
        assert response.json()["kind"] == "answer" and "no registra contradicciones" in response.json()["text"]


def test_offline_the_edit_chips_are_disabled_with_the_reason_and_search_chips_stay_enabled(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "db.sqlite3", offline=True))) as client:
        html = client.get("/cases/CASO-001/draft").text
        assert 'class="prompt" data-assist="ask" data-action="rewrite" disabled' in html and "necesita conexión" in html
        assert 'data-action="articles" disabled' not in html and 'data-action="gaps" disabled' not in html
