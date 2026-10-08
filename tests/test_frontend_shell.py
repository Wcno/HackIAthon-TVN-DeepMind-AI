"""G6 shell: layout, static assets, inbox, query states, methodology and offline guarantees."""

import re

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app, number, percent
from whoami.backend.settings import Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        yield client


def test_spanish_number_format():
    assert number(30823) == "30.823"
    assert number(1234567.5) == "1.234.567,50"
    assert percent(44.36) == "44,36 %"
    assert number(None) == "-"


def test_layout_has_nav_search_banner_and_local_assets(client):
    html = client.get("/inbox").text
    for label in ("Temas", "Calidad de datos", "Metodología"):
        assert f">{label}</a>" in html
    assert '>Consultas</a>' not in html
    assert 'role="search"' in html and 'action="/inbox"' in html
    assert "Demostración" in html
    assert 'href="/static/app.css"' in html and 'src="/static/htmx.min.js"' in html
    assert 'aria-current="page">Temas' in html


def test_static_assets_are_served(client):
    css = client.get("/static/app.css")
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/fonts/barlow-400-normal.woff2").status_code == 200


@pytest.mark.parametrize("path", ["/inbox", "/queries", "/quality", "/methodology", "/groups/G-001", "/missing-page"])
def test_no_remote_scripts_styles_or_fonts(client, path):
    html = client.get(path).text
    assert not re.findall(r"<(?:script|link)[^>]+(?:src|href)=[\"']https?://", html)
    assert "fonts.googleapis" not in html and "cdn." not in html


def selected_row_ids(html):
    return re.findall(r'<li class="row is-selected">.*?href="/(?:groups|cases)/([^"?]+)', html, re.S)


def test_inbox_is_master_detail_with_lead_filters_list_and_open_pane(client):
    ranked = client.app.state.editorial.inbox()
    html = client.get("/inbox").text
    assert '<article class="lead' in html and 'id="case"' in html and 'role="tabpanel"' in html
    assert 'name="topic"' in html and 'name="estado"' in html
    assert html.count('<li class="row') == len(ranked) - 1  # the lead is not repeated in the list
    assert ranked[0]["titulo"] in html.split('id="case"')[1]  # default selection is the lead
    assert html.count('aria-selected="true"') == 1


@pytest.mark.parametrize("path", ["/groups/G-003", "/groups/G-003/context", "/cases/CASO-003", "/cases/CASO-003/draft", "/cases/CASO-003/review"])
def test_deep_links_render_the_same_screen_with_the_item_selected(client, path):
    html = client.get(path).text
    assert '<article class="lead' in html and 'name="topic"' in html
    assert len(selected_row_ids(html)) == 1
    assert client.app.state.editorial.group("G-003")["titulo"] in html.split('id="case"')[1]


def test_deep_link_to_the_lead_highlights_the_lead_not_a_row(client):
    html = client.get("/groups/G-001").text
    assert selected_row_ids(html) == []
    assert 'class="lead is-selected"' in html


def test_htmx_tab_request_returns_only_the_pane(client):
    response = client.get("/cases/CASO-003/draft", headers={"HX-Request": "true", "HX-Target": "case"})
    assert 'role="tabpanel"' in response.text and 'role="tab"' in response.text
    for fragment in ("<main", "<html", '<article class="lead', 'name="topic"', 'class="rows"'):
        assert fragment not in response.text


def test_htmx_row_request_returns_list_and_pane_without_the_page(client):
    response = client.get("/cases/CASO-003", headers={"HX-Request": "true", "HX-Target": "desk"})
    assert 'class="rows"' in response.text and 'role="tabpanel"' in response.text
    assert "<main" not in response.text and '<article class="lead' not in response.text


def test_pane_is_marked_open_only_on_case_routes(client):
    assert "pane--open" not in client.get("/inbox").text
    assert "pane--open" in client.get("/groups/G-003").text


def test_filters_keep_the_selection_and_are_carried_by_links(client):
    ranked = client.app.state.editorial.inbox()
    topic = ranked[-1]["tema"]
    html = client.get(f"/groups/{ranked[-1]['id_grupo']}", params={"topic": topic}).text
    assert f"?topic={topic}" in html
    assert selected_row_ids(html)


def test_inbox_filters_by_topic_and_review_state(client):
    ranked = client.app.state.editorial.inbox()
    topic = ranked[-1]["tema"]
    html = client.get("/inbox", params={"topic": topic}).text
    assert html.count('<li class="row') == sum(1 for group in ranked if group["tema"] == topic)
    assert "No hay temas con estos filtros" in client.get("/inbox", params={"estado": "descartado"}).text


def test_groups_without_case_file_say_so_in_the_pane(client):
    without_case = [group for group in client.app.state.editorial.inbox() if not group["id_caso"]]
    if not without_case:
        pytest.skip("every group has a case file in this dataset")
    pane = client.get(f"/groups/{without_case[0]['id_grupo']}").text.split('id="case"')[1]
    assert "Este tema aún no tiene ficha de evidencia" in pane


def test_query_states(client):
    answers = client.app.state.repository.records("answer")
    by_state = {answer["estado"]: answer for answer in answers}
    assert "abstencion" in by_state
    html = client.get("/queries", params={"q": by_state["abstencion"]["consulta"]}).text
    assert "No hay evidencia suficiente para responder" in html and "Qué se necesitaría" in html
    if "respondida" in by_state:
        assert "Respuesta con evidencia" in client.get("/queries", params={"q": by_state["respondida"]["consulta"]}).text
    unavailable = client.get("/queries", params={"q": "Consulta nunca precalculada"})
    assert unavailable.status_code == 200
    assert "No hay una respuesta precalculada para esta consulta" in unavailable.text


def test_methodology_placeholder_and_styled_error(client):
    response = client.get("/methodology")
    assert response.status_code == 200 and "Metodología" in response.text
    missing = client.get("/groups/missing")
    assert missing.status_code == 404 and "page-card" in missing.text


def test_snapshot_line_above_the_lead_uses_quality_data_and_links_to_it(client):
    html = client.get("/inbox").text
    snapshot = html.split('class="snapshot"')[1].split("</p>")[0]
    assert "30.823 noticias leídas · 3.176 en la ventana de 30 días · 27.286 excluidas" in snapshot
    assert 'href="/quality"' in snapshot and "Ver calidad de datos" in snapshot
    assert html.index('class="snapshot"') < html.index('<article class="lead')


def test_snapshot_is_read_once_at_startup(tmp_path, monkeypatch):
    import whoami.backend.app as module

    calls = []
    original = module.snapshot_view
    monkeypatch.setattr(module, "snapshot_view", lambda directory: calls.append(directory) or original(directory))
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        client.get("/inbox")
        client.get("/groups/G-003")
    assert len(calls) == 1


def test_header_shows_the_data_cutoff_in_panama_time(client):
    header = client.get("/inbox").text.split("</header>")[0]
    assert re.search(r'<p class="corte">Corte: 7 oct 2026, 19:51</p>', header)


def test_lead_has_scorebar_dateline_and_no_coverage_counts(client):
    lead = client.get("/inbox").text.split('<article class="lead')[1].split("</article>")[0]
    assert 'class="scorebar"' in lead and lead.count("scorebar__seg--") == 5
    assert "Panamá, 5 oct" in lead


def test_rows_show_date_and_origin_count_in_prototype_wording(client):
    html = client.get("/inbox").text
    rows = html.split('class="rows"')[1].split('id="case"')[0]
    assert ">6 oct</span>" in rows
    assert "1 origen<" in rows and "2 orígenes<" in rows
    assert "medios" not in rows


def test_recirculated_group_is_dated_by_its_recirculation_in_panama_time(client):
    rows = client.get("/inbox").text.split('class="rows"')[1]
    row = rows.split("G-006")[0].rsplit("<li", 1)[-1] if "G-006" in rows else ""
    assert ">5 oct</span>" in rows and "17 dic" not in rows


def test_flag_requires_investigation_only_when_priority_high_and_evidence_insufficient(client):
    rows = client.get("/inbox").text.split('class="rows"')[1]
    items = rows.split("<li class=\"row")[1:]
    flagged = [item for item in items if "Requiere investigación" in item]
    assert len(flagged) == 1 and "Evidencia insuficiente" in flagged[0]
    assert client.get("/groups/G-001").text.split('<article class="lead')[1].split("</article>")[0].count("Requiere investigación") == 0


def test_synthetic_banner_is_hidden_on_quality_only(client):
    assert "Demostración con datos sintéticos" not in client.get("/quality").text
    assert "Demostración con datos sintéticos" in client.get("/inbox").text
