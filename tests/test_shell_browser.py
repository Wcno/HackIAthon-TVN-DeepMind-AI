"""Shell behaviour in a real browser: drawer, score popover, focus, tab titles and phone width."""

import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from whoami.backend.app import create_app
from whoami.backend.settings import Settings

pytestmark = pytest.mark.browser


@pytest.fixture
def server(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(create_app(Settings(database=tmp_path / "shell.sqlite3")), log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Browser fixture server failed to start"
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


@pytest.fixture
def browser_page():
    with sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("google-chrome-stable") or shutil.which("chromium")
        if not executable and Path("/opt/google/chrome/chrome").exists():
            executable = "/opt/google/chrome/chrome"
        if not executable and not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Install Chromium with: uv run playwright install chromium")
        browser = playwright.chromium.launch(executable_path=executable, args=["--no-sandbox"])
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser_page):
    page = browser_page.new_page(viewport={"width": 1440, "height": 1000})
    yield page
    page.close()


def test_escape_closes_the_source_drawer_and_returns_focus_to_the_citation(page, server):
    page.goto(f"{server}/cases/CASO-001")
    drawer = page.locator("#source-panel")
    expect(drawer).not_to_have_class("drawer is-open")
    citation = page.locator("a.cite").first
    citation.click()
    expect(drawer).to_have_class("drawer is-open")
    expect(drawer).to_be_focused()
    assert page.locator("#source-body").inner_text().count("Fecha publicacion") == 0
    page.keyboard.press("Escape")
    expect(drawer).not_to_have_class("drawer is-open")
    expect(citation).to_be_focused()


def test_close_button_closes_the_drawer(page, server):
    page.goto(f"{server}/groups/G-001")
    page.locator("a.member__hit").first.click()
    expect(page.locator("#source-panel")).to_have_class("drawer is-open")
    page.get_by_role("button", name="Cerrar fuente").click()
    expect(page.locator("#source-panel")).not_to_have_class("drawer is-open")


def test_score_popover_closes_with_escape_and_with_an_outside_click(page, server):
    page.goto(f"{server}/cases/CASO-001")
    popover = page.locator("details.relative")
    summary = popover.locator("summary")
    summary.click()
    expect(popover).to_have_attribute("open", "")
    page.keyboard.press("Escape")
    expect(popover).not_to_have_attribute("open", "")
    summary.click()
    expect(popover).to_have_attribute("open", "")
    page.locator(".tabs").click(position={"x": 400, "y": 5})
    expect(popover).not_to_have_attribute("open", "")


def test_tab_swaps_update_the_document_title(page, server):
    page.goto(f"{server}/cases/CASO-001")
    page.get_by_role("tab", name="Borrador").click()
    expect(page).to_have_title("Borrador · El Canal reduce los tránsitos diarios por la sequía · TVN DeepMind AI")
    page.get_by_role("tab", name="Revisión").click()
    expect(page).to_have_title("Revisión · El Canal reduce los tránsitos diarios por la sequía · TVN DeepMind AI")


def test_skip_link_is_reachable_first_and_phone_popover_fits(browser_page, server):
    page = browser_page.new_page(viewport={"width": 390, "height": 800})
    page.goto(f"{server}/groups/G-001")
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Saltar al contenido")).to_be_focused()
    page.goto(f"{server}/cases/CASO-001")
    page.locator("details.relative summary").click()
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    box = page.locator(".popover").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390
    page.close()


@pytest.mark.parametrize("width", [390, 641, 800, 961, 972, 1100, 1280])
def test_score_popover_stays_inside_the_viewport_and_its_box(browser_page, server, width):
    page = browser_page.new_page(viewport={"width": width, "height": 900})
    page.goto(f"{server}/cases/CASO-001")
    page.locator("details.relative summary").first.click()
    box = page.locator(".popover").first.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    case = page.locator(".case").first.bounding_box()
    assert box["x"] + box["width"] <= case["x"] + case["width"]
    assert page.evaluate("[...document.querySelectorAll('.popover *')].every(e => e.getBoundingClientRect().right <= document.querySelector('.popover').getBoundingClientRect().right + 1)")
    page.close()


@pytest.mark.parametrize("width", [320, 390, 600, 972, 1100])
def test_every_nav_item_is_reachable_without_page_overflow(browser_page, server, width):
    page = browser_page.new_page(viewport={"width": width, "height": 800})
    page.goto(f"{server}/inbox")
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for link in page.locator("nav.nav a").all():
        box = link.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, link.inner_text()
    page.close()
