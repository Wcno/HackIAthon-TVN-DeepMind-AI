"""Inbox behaviour: pagination, filters and search that cooperate, case-file status and page weight."""

import re

import pytest
from fastapi.testclient import TestClient

import whoami.backend.app as module
from whoami.backend.app import create_app
from whoami.backend.settings import Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        yield client


def row_ids(html):
    return re.findall(r'<li class="row[^"]*">.*?href="/(?:groups|cases)/([^"?]+)', html, re.S)


def test_inbox_lists_a_page_of_rows_and_offers_more(client, monkeypatch):
    monkeypatch.setattr(module, "INBOX_PAGE_SIZE", 2)
    ranked = client.app.state.editorial.inbox()
    html = client.get("/inbox").text
    assert len(row_ids(html)) == 2
    assert 'href="/inbox?desde=2"' in html and 'hx-get="/inbox?desde=2"' in html
    assert f"Ver más temas ({len(ranked) - 1 - 2} restantes)" in html and f"{len(ranked)} temas<" in html


def test_ver_mas_fragment_returns_only_the_next_rows_and_the_next_link(client, monkeypatch):
    monkeypatch.setattr(module, "INBOX_PAGE_SIZE", 2)
    first = row_ids(client.get("/inbox").text)
    fragment = client.get("/inbox?desde=2", headers={"HX-Request": "true", "HX-Target": "more-rows"}).text
    assert len(row_ids(fragment)) == 2 and not set(first) & set(row_ids(fragment))
    assert "<main" not in fragment and 'name="topic"' not in fragment
    assert 'hx-get="/inbox?desde=4"' in fragment


def test_last_page_has_no_ver_mas_and_a_plain_load_keeps_earlier_pages(client, monkeypatch):
    monkeypatch.setattr(module, "INBOX_PAGE_SIZE", 2)
    total = len(client.app.state.editorial.inbox()) - 1
    html = client.get("/inbox?desde=4").text
    assert len(row_ids(html)) == total and "Ver más" not in html


def test_case_and_group_pages_do_not_render_the_whole_inbox(client, monkeypatch):
    monkeypatch.setattr(module, "INBOX_PAGE_SIZE", 2)
    for path in ("/cases/CASO-003", "/groups/G-007", "/cases/CASO-003/draft"):
        assert len(row_ids(client.get(path).text)) <= 2


def test_ver_mas_keeps_the_active_filters(client, monkeypatch):
    monkeypatch.setattr(module, "INBOX_PAGE_SIZE", 1)
    html = client.get("/inbox", params={"estado": "sin_ficha"}).text
    assert 'href="/inbox?estado=sin_ficha&amp;desde=1"' in html


def test_topic_and_estado_filters_keep_the_search_text(client):
    form = client.get("/inbox", params={"q": "tarifas"}).text.split('class="filters"')[1].split("</form>")[0]
    assert '<input type="hidden" name="q" value="tarifas">' in form


def test_search_keeps_topic_and_estado(client):
    header = client.get("/inbox", params={"topic": "turismo", "estado": "requiere_evidencia"}).text.split("</header>")[0]
    assert '<input type="hidden" name="topic" value="turismo">' in header
    assert '<input type="hidden" name="estado" value="requiere_evidencia">' in header
    assert 'type="hidden"' not in client.get("/inbox").text.split("</header>")[0]


def test_htmx_filter_swap_refreshes_the_search_box(client):
    fragment = client.get("/inbox", params={"q": "tarifas"}, headers={"HX-Request": "true", "HX-Target": "screen"}).text
    assert 'id="search-form"' in fragment and 'hx-swap-oob="true"' in fragment and 'value="tarifas"' in fragment


def test_groups_without_a_case_file_show_sin_ficha_in_the_list(client):
    rows = client.get("/inbox").text.split('class="rows"')[1]
    items = {match.group(1): match.group(0) for match in re.finditer(r'<li class="row[^"]*">.*?href="/(?:groups|cases)/([^"?]+).*?</li>', rows, re.S)}
    assert "Sin ficha" in items["G-007"] and "Nuevo" not in items["G-007"]
    assert "Sin ficha" not in items["CASO-004" if "CASO-004" in items else "G-004"]


def test_estado_filter_offers_sin_ficha_and_applies_it(client):
    html = client.get("/inbox", params={"estado": "sin_ficha"}).text
    assert '<option value="sin_ficha" selected>Sin ficha</option>' in html
    assert sorted(row_ids(html)) == ["G-006", "G-007"]


def test_nuevo_means_a_case_file_exists_and_is_unreviewed(client):
    assert row_ids(client.get("/inbox", params={"estado": "nuevo"}).text) == ["CASO-004"]


def test_case_header_carries_the_investigation_flag_like_the_list(client):
    header = client.get("/groups/G-003").text.split('class="case__head"')[1].split("</header>")[0]
    assert "Requiere investigación" in header
    assert "Requiere investigación" not in client.get("/groups/G-001").text.split('class="case__head"')[1].split("</header>")[0]


@pytest.mark.parametrize("params", [{"topic": "no-existe"}, {"estado": "no-existe"}, {"topic": "no-existe", "estado": "no-existe"}])
def test_invalid_filter_values_are_ignored_consistently(client, params):
    baseline = client.get("/inbox").text
    html = client.get("/inbox", params=params).text
    assert row_ids(html) == row_ids(baseline) and '<article class="lead' in html
    assert "no-existe" not in html


def test_the_lead_band_is_hidden_while_filtering(client):
    assert '<article class="lead' in client.get("/inbox").text
    for params in ({"topic": "turismo"}, {"estado": "nuevo"}, {"q": "a"}):
        html = client.get("/inbox", params=params).text
        assert '<article class="lead' not in html


def test_filtered_list_counts_every_match_and_includes_the_top_group(client):
    html = client.get("/inbox", params={"estado": "en_revision"}).text
    assert row_ids(html)[0] == "CASO-001" and "2 temas<" in html


def test_empty_results_do_not_ask_to_pick_from_an_empty_list(client):
    html = client.get("/inbox", params={"estado": "descartado"}).text
    assert "Elige un tema de la lista" not in html and "No hay temas con estos filtros" in html


def test_scores_always_show_two_decimals(client):
    html = client.get("/inbox").text
    assert '<span class="score__value">70,00</span>' in html and '<span class="score__value">93,75</span>' in html
    assert '<span class="score__value">70,00</span>' in client.get("/groups/G-003").text


def test_methodology_picker_is_short_and_searchable(client, monkeypatch):
    monkeypatch.setattr(module, "METHODOLOGY_OPTIONS", 3)
    ranked = client.app.state.editorial.inbox()
    page = client.get("/methodology").text
    assert page.count("<option") == 3
    last = ranked[-1]
    chosen = client.get("/methodology", params={"grupo": last["id_grupo"]}).text
    assert f'value="{last["id_grupo"]}" selected' in chosen and chosen.count("<option") == 4
    found = client.get("/methodology", params={"q": last["titulo"][:12]}).text
    assert f'<p class="example__title">{last["titulo"]}</p>' in found and 'name="q"' in found


def test_methodology_search_without_matches_says_so(client):
    page = client.get("/methodology", params={"q": "zzzz-sin-coincidencias"}).text
    assert "Ningún tema coincide" in page
