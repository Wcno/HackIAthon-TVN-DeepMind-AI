"""Real-browser decisions use only the tiny fixture pool, never actual evaluation judgments."""

import pytest
from playwright.sync_api import expect

from test_editor_browser import page, serve
from test_model_comparison import snapshot
from whoami.model_comparison import create_review_app, ReviewStore

pytestmark = pytest.mark.browser


@pytest.fixture
def comparison_server(tmp_path):
    frozen = snapshot()
    database = tmp_path / "fixture-human.sqlite3"
    for url in serve(create_review_app(frozen, database)):
        yield url, ReviewStore(database, frozen)


def test_blind_review_can_save_unknown_and_revisit_without_horizontal_overflow(page, comparison_server):
    url, store = comparison_server
    page.goto(url)
    expect(page.get_by_role("heading", name="Revisión humana", exact=True)).to_be_visible()
    assert "fp32" not in page.locator("body").inner_text()
    assert "q4" not in page.locator("body").inner_text()
    page.get_by_label("Responsable").fill("Fixture browser reviewer")
    page.get_by_label("Decisión").select_option("unknown")
    page.get_by_role("button", name="Guardar y continuar").click()
    expect(page.get_by_text("1 / 7 decisiones guardadas. Los candidatos están ocultos.", exact=True)).to_be_visible()
    assert next(iter(store.labels().values()))["grade"] == "unknown"
    page.reload()
    expect(page.get_by_text("1 / 7 decisiones guardadas. Los candidatos están ocultos.", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
