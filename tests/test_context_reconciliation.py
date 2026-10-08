"""G7: the official-context card says what the indicator measures and never implies it confirms a headline figure."""

from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings


def context_page(tmp_path, group_id):
    with TestClient(create_app(Settings(database=tmp_path / "db.sqlite3"))) as client:
        return client.get(f"/groups/{group_id}/context").text


def test_context_card_states_what_is_measured_and_its_period(tmp_path):
    page = context_page(tmp_path, "G-002")
    assert "Qué mide" in page
    assert "IPC, variación interanual (nacional urbano)" in page
    assert "% interanual" in page and "2026-08" in page and "2024=100" in page


def test_context_card_does_not_equate_the_indicator_with_headline_figures(tmp_path):
    page = context_page(tmp_path, "G-002")
    assert "no es automáticamente la misma medición" in page
    assert "Verifica en la fuente" in page


def test_card_without_a_base_omits_it(tmp_path):
    page = context_page(tmp_path, "G-001")
    assert "Qué mide" in page and "Base" not in page.split("Qué mide")[1].split("</section>")[0]
