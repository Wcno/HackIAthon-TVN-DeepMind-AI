"""G6: the case workspace (tabs, source panel, score breakdown, review form errors)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings

TABS = ("Historia", "Cobertura", "Contexto", "Borrador", "Revisión")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        yield client


def decision(client, **overrides):
    version = client.app.state.repository.case("CASO-001")["version"]
    data = {"state": "requiere_evidencia", "actor": "Ana Reyes", "expected_version": version, "note": "Revisado"}
    return client.post("/cases/CASO-001/review", data={**data, **overrides})


@pytest.mark.parametrize("path", ["/cases/CASO-001", "/groups/G-001", "/groups/G-001/context",
                                  "/cases/CASO-001/draft", "/cases/CASO-001/review"])
def test_every_workspace_page_shows_the_five_tabs(client, path):
    html = client.get(path).text
    for tab in TABS:
        assert re.search(rf'role="tab"[^>]*>\s*{tab}\s*<', html), (path, tab)
    assert html.count('aria-selected="true"') == 1


def test_case_page_has_score_breakdown_and_source_links(client):
    html = client.get("/cases/CASO-001").text
    assert "<details" in html
    assert "Relevancia" in html and "Evidencia disponible" in html
    assert "/evidence/N-2cf673d2b74a" in html


def test_evidence_page_is_the_source_panel(client):
    html = client.get("/evidence/N-2cf673d2b74a").text
    assert "Fuente original" in html and "Panamá" in html


def test_draft_shows_package_and_cited_claims(client):
    html = client.get("/cases/CASO-001/draft").text
    assert "El Canal reduce a 32 los tránsitos diarios por la sequía" in html
    assert "/evidence/WB-PAN-NE.EXP.GNFS.ZS-2024" in html


def test_review_success_persists_and_bumps_version(client):
    before = client.app.state.repository.case("CASO-001")["version"]
    response = decision(client)
    assert response.status_code == 200
    assert "Ana Reyes" in response.text
    case = client.app.state.repository.case("CASO-001")
    assert case["version"] == before + 1 and case["estado_revision"] == "requiere_evidencia"


def test_stale_version_shows_conflict_inside_the_form(client):
    stale = client.app.state.repository.case("CASO-001")["version"]
    assert decision(client, state="descartado").status_code == 200
    response = decision(client, state="en_revision", expected_version=stale)
    assert response.status_code == 409
    assert re.search(r'<form[^>]*>.*role="alert".*Otra persona actualizó.*</form>', response.text, re.S)
    assert client.app.state.repository.case("CASO-001")["estado_revision"] == "descartado"


def test_empty_actor_shows_validation_error_inside_the_form(client):
    response = decision(client, actor="")
    assert response.status_code == 422
    assert re.search(r'<form[^>]*>.*role="alert".*nombre del responsable.*</form>', response.text, re.S)
    assert "Revisión humana" in response.text


def test_invalid_transition_shows_message_inside_the_form(client):
    response = decision(client, state="nuevo")
    assert response.status_code == 422
    assert re.search(r'<form[^>]*>.*role="alert".*</form>', response.text, re.S)


def test_draft_blocks_show_budget_meters_and_copy_buttons(client):
    html = client.get("/cases/CASO-001/draft").text
    assert len(re.findall(r'class="budget[ "]', html)) == 3
    assert re.search(r"/ 250 palabras", html) and re.search(r"/ 45-60 s", html) and re.search(r"/ 80 palabras", html)
    assert html.count("Copiar</button>") >= 4
    script = client.get("/static/editor.js").text
    assert "Copiado" in script and "navigator.clipboard" in script


def test_budget_flags_over_and_under_limits():
    from whoami.backend.presentation import budget

    assert budget(300, 250, "palabras")["state"] == "is-over"
    assert budget(30, 60, "s", 45)["state"] == "is-under"
    assert budget(50, 60, "s", 45)["state"] == ""
    assert budget(125, 250, "palabras")["percent"] == 50
    assert budget(500, 250, "palabras")["percent"] == 100


def test_script_budget_uses_spoken_pace(client):
    from whoami.backend.presentation import spoken_seconds

    assert spoken_seconds(" ".join(["x"] * 125)) == 50


def test_draft_has_no_per_sentence_claim_tags(client):
    assert 'class="annotated"' not in client.get("/cases/CASO-001/draft").text


def test_case_header_entrance_does_not_clip_the_score_popover():
    stylesheet = (Path(__file__).parents[1] / "src/whoami/backend/static/src/app.css").read_text(encoding="utf-8")
    rule = re.search(r"\.case\.is-entering \.case__head \{ animation: ([^;]+);", stylesheet)
    assert rule and rule.group(1).endswith("backwards")
