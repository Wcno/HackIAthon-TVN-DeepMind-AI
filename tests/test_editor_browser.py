"""Browser tests exercise the real app; only Gemini's external HTTP boundary is fake."""

import json
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from whoami.backend.app import create_app
from whoami.backend.settings import Settings

pytestmark = pytest.mark.browser


@pytest.fixture
def editor_server(tmp_path, request):
    offline = getattr(request, "param", False)

    def provider(http_request):
        if offline:
            pytest.fail("Offline browser flow attempted a Gemini request")
        content = {"kind": "suggestion", "field": "titulo", "text": "Un titular más directo.",
                   "options": ["Canal de Panamá: 32 tránsitos diarios ante la sequía"],
                   "citations": [{"id_evidencia": "N-2cf673d2b74a", "campo": "titulo", "pasaje": "32"}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    settings = Settings(database=tmp_path / "browser.sqlite3", offline=offline, gemini_api_key="fixture-key")
    app = create_app(settings, gemini_transport=httpx.MockTransport(provider))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Browser fixture server failed to start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("google-chrome-stable") or shutil.which("chromium")
        if not executable and Path("/opt/google/chrome/chrome").exists():
            executable = "/opt/google/chrome/chrome"
        if not executable and not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Install Chromium with: uv run playwright install chromium")
        browser = playwright.chromium.launch(executable_path=executable, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            yield page
            assert not errors
        finally:
            browser.close()


def test_editor_add_remove_save_reload_and_htmx_navigation(page, editor_server):
    page.goto(f"{editor_server}/cases/CASO-001/draft")
    title = page.locator('textarea[data-key="titulo"]')
    title.fill("Un titular editado por la redacción")
    questions = page.locator('textarea[data-key="preguntas"]')
    page.get_by_role("button", name="Añadir pregunta", exact=True).click()
    expect(questions).to_have_count(4)
    expect(questions.last).to_be_focused()
    questions.last.fill("¿Cuándo se revisará la medida?")
    page.get_by_role("button", name="Quitar pregunta 2", exact=True).click()
    expect(questions).to_have_count(3)
    expect(questions.last).to_have_attribute("aria-label", "Pregunta 3")
    page.get_by_role("button", name="Guardar cambios", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Cambios guardados")).to_be_visible()
    page.reload()
    expect(title).to_have_value("Un titular editado por la redacción")
    expect(questions.last).to_have_value("¿Cuándo se revisará la medida?")
    page.get_by_role("tab", name="Historia", exact=True).click()
    expect(page.locator('[data-editor]')).to_have_count(0)
    expect(page.locator('.draft-assistant')).to_have_count(0)
    page.get_by_role("tab", name="Borrador", exact=True).click()
    expect(title).to_have_value("Un titular editado por la redacción")
    expect(page.locator('.draft-assistant')).to_have_count(1)


def test_assistant_apply_and_sources_are_real_controls(page, editor_server):
    page.goto(f"{editor_server}/cases/CASO-001/draft")
    title = page.locator('textarea[data-key="titulo"]')
    original = title.input_value()
    page.get_by_role("button", name="Propón 3 titulares alternativos", exact=True).click()
    apply = page.get_by_role("button", name="Aplicar", exact=True)
    expect(apply).to_be_visible()
    expect(title).to_have_value(original)
    apply.click()
    expect(title).to_have_value("Canal de Panamá: 32 tránsitos diarios ante la sequía")
    page.get_by_role("button", name="Guardar cambios", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Cambios guardados")).to_be_visible()
    page.reload()
    expect(title).to_have_value("Canal de Panamá: 32 tránsitos diarios ante la sequía")
    page.goto(f"{editor_server}/cases/CASO-002/draft")
    page.locator('#ask-input').fill("Busca noticias sobre el Canal")
    page.locator('.ask button[type="submit"]').click()
    cards = page.locator('.result')
    expect(cards).to_have_count(4)
    cards.first.get_by_role("button", name="Ver fuente", exact=True).click()
    expect(page.locator('.editor-source')).to_be_visible()
    expect(page.locator('.editor-source .drawer__title')).to_contain_text("Canal")
    page.get_by_role("button", name="Volver a Co-News", exact=True).click()
    cards.first.get_by_role("button", name="Añadir a la ficha", exact=True).click()
    expect(cards.first.get_by_role("button", name="Añadida · sin guardar", exact=True)).to_be_disabled()
    page.get_by_role("button", name="Guardar cambios", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Cambios guardados")).to_be_visible()
    page.reload()
    expect(page.locator('textarea[data-key="fuentes_y_verificaciones"]').last).to_contain_text("Revisar fuente añadida")


def test_copy_uses_edited_text_and_selects_it_when_clipboard_fails(page, editor_server):
    page.goto(f"{editor_server}/cases/CASO-001/draft")
    field = page.locator('textarea[data-key="titulo"]')
    field.fill("Copiar el texto editado")
    page.evaluate("() => { navigator.clipboard.writeText = async text => { window.copiedText = text; }; }")
    copy = page.locator('[data-section="titulo"] button[data-edit="copy"]')
    copy.click()
    expect(copy).to_have_text("Copiado")
    assert page.evaluate("window.copiedText") == "Copiar el texto editado"
    page.evaluate("() => { navigator.clipboard.writeText = async () => { throw new Error('denied'); }; }")
    expect(copy).to_have_text("Copiar", timeout=3000)
    copy.click()
    expect(copy).to_have_text("Selecciona y copia")
    assert field.evaluate("e => e.selectionStart === 0 && e.selectionEnd === e.value.length")


def test_unsaved_edits_are_not_lost_by_a_tab_change(page, editor_server):
    page.goto(f"{editor_server}/cases/CASO-001/draft")
    title = page.locator('textarea[data-key="titulo"]')
    title.fill("No perder este titular")
    page.get_by_role("tab", name="Historia", exact=True).click()
    expect(title).to_have_value("No perder este titular")
    expect(page.get_by_role("alert")).to_contain_text("Guarda o descarta")
    page.get_by_role("button", name="Descartar cambios", exact=True).click()
    page.get_by_role("tab", name="Historia", exact=True).click()
    expect(page.locator('[data-editor]')).to_have_count(0)


@pytest.mark.parametrize("editor_server", [True], indirect=True)
def test_mobile_offline_assistant_abstains_without_overflow(page, editor_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{editor_server}/cases/CASO-001/draft")
    page.get_by_role("button", name="Abrir Co-News", exact=True).click()
    expect(page.locator('.draft-assistant')).to_be_visible()
    page.locator('#ask-input').fill("¿Qué pasará mañana?")
    page.locator('.ask button[type="submit"]').click()
    expect(page.locator('.reply')).to_contain_text("Sin conexión")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Cerrar", exact=True).click()
    expect(page.locator('.draft-assistant')).to_be_hidden()
