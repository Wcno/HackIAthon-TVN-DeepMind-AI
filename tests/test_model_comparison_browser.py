"""Real-browser decisions use only the tiny fixture pool, never actual evaluation judgments."""

import pytest
from playwright.sync_api import expect

from test_editor_browser import page, serve
from test_model_comparison import snapshot, agent_reviews
from whoami.model_comparison import create_review_app, ReviewStore, score_agent_reviews

pytestmark = pytest.mark.browser


@pytest.fixture
def comparison_server(tmp_path, request):
    frozen = snapshot()
    database = tmp_path / "fixture-human.sqlite3"
    report = score_agent_reviews(frozen, agent_reviews(frozen)) if getattr(request, "param", False) else None
    for url in serve(create_review_app(frozen, database, agent_report=report)):
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


@pytest.mark.parametrize("comparison_server", [True], indirect=True)
def test_agent_completion_folds_human_form_and_opens_origin_labeled_results(page, comparison_server):
    url, store = comparison_server
    page.goto(url)
    expect(page.get_by_text("Evaluación del agente completada: 7 / 7.", exact=True)).to_be_visible()
    expect(page.get_by_label("Responsable")).not_to_be_visible()
    page.get_by_role("link", name="Ver comparación de modelos", exact=True).click()
    expect(page.get_by_role("heading", name="Comparación evaluada por el agente", exact=True)).to_be_visible()
    assert "No se presentan como revisión humana" in page.locator("body").inner_text()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert store.labels() == {}
