"""G6 review fixes: honest query states, field-specific form errors, derived score weights, source drawer, copy, list badge."""

import logging
import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings
from whoami.contracts import SCORE_WEIGHTS


@pytest.fixture
def settings(tmp_path):
    return Settings(database=tmp_path / "editorial.sqlite3")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def online_client(settings, provider, **changes):
    return TestClient(create_app(replace(settings, offline=False, **changes), query_provider=provider))


def test_offline_query_without_precomputed_answer_is_a_spanish_abstention(client):
    response = client.get("/queries", params={"q": "Consulta nunca precalculada"})
    assert response.status_code == 200
    assert "No hay una respuesta precalculada para esta consulta" in response.text
    assert "Consulta nunca precalculada" in response.text
    for example in client.app.state.repository.records("answer"):
        assert example["consulta"] in response.text
    assert "sin conexión: solo" not in response.text


def test_online_timeout_is_not_reported_as_offline_and_hides_the_internal_detail(settings, caplog):
    import asyncio

    async def slow(query, gemini, repository):
        await asyncio.sleep(60)

    with online_client(settings, slow, generation_timeout=0.03) as client, caplog.at_level(logging.WARNING):
        response = client.get("/queries", params={"q": "New query"})
    assert response.status_code == 503
    assert "Sin conexión" not in response.text
    assert "La consulta no pudo completarse" in response.text
    assert "deadline" not in response.text
    assert "deadline" in caplog.text


def test_invalid_pipeline_answer_hides_the_internal_detail(settings, caplog):
    async def broken(query, gemini, repository):
        return {"id_consulta": "Q", "consulta": query, "estado": "respondida", "respuesta": "x",
                "citas": [{"id_evidencia": "N-missing", "campo": "titulo", "pasaje": "x"}]}

    with online_client(settings, broken) as client, caplog.at_level(logging.WARNING):
        response = client.get("/queries", params={"q": "New query"})
    assert response.status_code == 503
    assert "Sin conexión" not in response.text and "invalid answer" not in response.text
    assert "invalid answer" in caplog.text


def review_post(client, **overrides):
    version = client.app.state.repository.case("CASO-001")["version"]
    data = {"state": "requiere_evidencia", "actor": "Ana Reyes", "expected_version": version, "note": "Nota intacta"}
    return client.post("/cases/CASO-001/review", data={**data, **overrides})


@pytest.mark.parametrize(("overrides", "expected"), [
    ({"state": "inventado"}, "decisión"),
    ({"actor": "   "}, "responsable"),
    ({"expected_version": "0"}, "versión"),
])
def test_review_validation_error_names_the_failing_field(client, overrides, expected):
    response = review_post(client, **overrides)
    assert response.status_code == 422
    error = re.search(r'class="form-error"[^>]*>(.*?)</p>', response.text, re.S).group(1)
    assert expected in error
    assert ("responsable" in error) == (expected == "responsable")
    assert "Nota intacta" in response.text
    if "actor" not in overrides:
        assert 'value="Ana Reyes"' in response.text


def test_score_popover_renders_names_and_weights_from_the_contract(settings, monkeypatch):
    from whoami.backend import reports

    with TestClient(create_app(settings)) as client:
        monkeypatch.setattr(reports, "SCORE_WEIGHTS", {**SCORE_WEIGHTS, "R": 31})
        monkeypatch.setitem(reports.COMPONENTS, "R", ("Relevancia renombrada", "x"))
        html = client.get("/cases/CASO-001").text
    assert "Relevancia renombrada" in html and "/ 31</td>" in html
    for weight in list(SCORE_WEIGHTS.values())[1:]:
        assert f"/ {weight}</td>" in html


@pytest.mark.parametrize("path", ["/cases/CASO-001", "/groups/G-001/context", "/cases/CASO-001/draft"])
def test_failed_source_load_shows_a_message_inside_the_drawer(client, path):
    html = client.get(path).text
    case = re.search(r'<section class="case[^"]*" id="case"[^>]*>', html).group(0)
    assert "hx-on::response-error" in case and "Fuente no disponible" in case
    assert 'id="source-body"' in html


def test_missing_evidence_is_a_404_the_drawer_can_react_to(client):
    assert client.get("/evidence/NO-EXISTE", headers={"HX-Request": "true"}).status_code == 404


def test_copy_button_confirms_only_after_the_clipboard_resolves_and_falls_back_to_selection(client):
    html = client.get("/cases/CASO-001/draft").text
    handler = re.search(r'data-copy="[^"]*"\s+hx-on:click="([^"]*)"', html).group(1)
    assert handler.index("writeText") < handler.index(".then(") < handler.index("Copiado")
    assert "Selecciona y copia" in handler and "selectAllChildren" in handler
    assert "navigator.clipboard ?" in handler


def test_successful_review_updates_the_list_row_badge_out_of_band(client):
    group_id = client.app.state.repository.case("CASO-001")["id_grupo"]
    row = f"review-badge-{group_id}"
    before = client.get("/cases/CASO-001/review").text
    form = re.search(r'<form class="decide"[^>]*>', before).group(0)
    assert f"#{row}" in re.search(r'hx-select-oob="([^"]*)"', form).group(1)
    response = review_post(client)
    assert response.status_code == 200
    badge = re.search(rf'id="(?:lead-)?{row}"[^>]*>(.*?)</span>', response.text, re.S).group(1)
    assert "Requiere evidencia" in badge
