"""TVN coverage in the redesigned UI: inbox rows and filter, group pane, and the Generar ficha panel."""

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings
from test_frontend_inbox import row_ids

#: Row links go to the case file when there is one: G-003 (covered) and G-001 (new for TVN) have theirs, G-006 (covered) has none.
COVERED, COVERED_NO_CASE, NOVEL = "CASO-003", "G-006", "CASO-001"
REASON = "Ya publicado por TVN: no es un descubrimiento externo."


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        yield client


def test_the_inbox_lists_every_topic_so_each_case_file_stays_reachable(client):
    ids = row_ids(client.get("/inbox", params={"cobertura": ""}).text)
    assert {COVERED, COVERED_NO_CASE} <= set(ids)


def test_the_new_for_tvn_filter_leaves_out_covered_topics(client):
    ids = row_ids(client.get("/inbox", params={"cobertura": "nuevo"}).text)
    assert "CASO-002" in ids and COVERED not in ids and COVERED_NO_CASE not in ids


def test_the_covered_filter_lists_only_covered_topics(client):
    ids = row_ids(client.get("/inbox", params={"cobertura": "cubierto"}).text)
    assert COVERED_NO_CASE in ids and NOVEL not in ids


def test_rows_say_what_the_tvn_comparison_found(client):
    html = client.get("/inbox").text
    assert "Cubierto por TVN" in html and "TVN sin comprobar" in html


def test_the_coverage_filter_is_kept_by_the_other_filters(client):
    html = client.get("/inbox", params={"cobertura": "cubierto"}).text
    assert '<option value="cubierto" selected>' in html


def test_the_group_pane_shows_the_tvn_reason(client):
    html = client.get("/groups/G-003").text
    assert "Cobertura de TVN" in html and REASON in html


def test_the_group_pane_lists_possible_updates_with_their_passage(client, monkeypatch):
    editorial = client.app.state.editorial
    original = editorial.group

    def with_update(group_id):
        group = original(group_id)
        coverage = group["cobertura_tvn"] | {"estado": "dato_nuevo", "pasajes_nuevos": [
            {"id_evidencia": "N-abc", "campo": "titulo", "pasaje": "limita a 32 los tránsitos"}]}
        return group | {"cobertura_tvn": coverage}

    monkeypatch.setattr(editorial, "group", with_update)
    html = client.get("/groups/G-001").text
    assert "Posible actualización" in html and "limita a 32 los tránsitos" in html and 'href="/evidence/N-abc"' in html


def test_generar_ficha_on_a_covered_topic_shows_the_tvn_reason_first(client):
    panel = client.get(f"/groups/{COVERED_NO_CASE}").text.split('id="case-file-generator"')[1]
    assert REASON in panel
    assert panel.index(REASON) < panel.index("Generar ficha")

