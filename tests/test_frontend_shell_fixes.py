"""QA batch C: browser titles, skip link, Spanish error pages, plurals, source labels, offline flag and terminology."""

import re

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        yield client


def page_title(html):
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1)


@pytest.mark.parametrize("path, section", [
    ("/cases/CASO-001", "Historia"), ("/groups/G-001", "Cobertura"), ("/groups/G-001/context", "Contexto"),
    ("/cases/CASO-001/draft", "Borrador"), ("/cases/CASO-001/review", "Revisión"),
])
def test_every_case_tab_names_the_topic_in_the_page_title(client, path, section):
    title = page_title(client.get(path).text)
    assert title.startswith(f"{section} · ") and "El Canal" in title and title.endswith("TVN DeepMind AI")


@pytest.mark.parametrize("path", ["/cases/CASO-001/draft", "/groups/G-001/context"])
def test_htmx_tab_swaps_carry_the_new_title(client, path):
    html = client.get(path, headers={"HX-Request": "true", "HX-Target": "case"}).text
    assert page_title(html).startswith(("Borrador · ", "Contexto · "))


def test_skip_link_is_the_first_focusable_element_and_targets_main(client):
    html = client.get("/inbox").text
    assert html.index('class="skip-link"') < html.index('class="brand"')
    assert 'href="#screen"' in html and '<main id="screen" tabindex="-1"' in html


def test_lead_photo_credit_is_not_a_tab_stop_before_the_card_link(client):
    lead = client.get("/inbox").text.split('<article class="lead')[1].split("</article>")[0]
    credit = re.findall(r'<figcaption class="photo__credit"><a [^>]*>', lead)
    assert all('tabindex="-1"' in link for link in credit)


@pytest.mark.parametrize("path, heading, message", [
    ("/groups/G-nope", "Tema no encontrado", "No encontramos este tema"),
    ("/cases/CASO-nope", "Ficha no encontrada", "No encontramos esta ficha"),
    ("/evidence/NOPE", "Fuente no encontrada", "No encontramos esta fuente"),
])
def test_unknown_records_get_a_spanish_page_with_chrome_and_a_way_back(client, path, heading, message):
    response = client.get(path)
    assert response.status_code == 404
    assert heading in response.text and message in response.text
    assert "Unknown" not in response.text and 'class="strap"' in response.text and 'href="/inbox"' in response.text


def test_unknown_routes_get_a_spanish_html_page_but_the_api_keeps_json(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404 and "text/html" in response.headers["content-type"]
    assert "No encontramos esta página" in response.text and 'class="strap"' in response.text
    api = client.get("/api/no-such-endpoint")
    assert api.status_code == 404 and api.headers["content-type"].startswith("application/json")


def test_counters_agree_in_number_with_their_quantity(client):
    one = client.get("/cases/CASO-003").text
    assert "1 noticia · 1 medio · 1 procedencia independiente<" in one
    many = client.get("/cases/CASO-001").text
    assert re.search(r"[2-9] noticias · \d+ medios? · \d+ procedencias? independientes?<", many)
    tally = client.get("/groups/G-003").text.split('class="tally"')[1].split("</div>")[0]
    assert "</strong>noticia<" in tally and "</strong>procedencia independiente<" in tally


def test_case_sources_list_headline_and_outlet_not_raw_ids(client):
    sources = client.get("/cases/CASO-001").text.split('class="sources__list"')[1].split("</ol>")[0]
    assert "El Canal de Panamá reduce a 32 los tránsitos diarios" in sources
    assert not re.search(r">N-[0-9a-f]{12}<", sources)


def test_query_sources_list_headline_not_raw_ids(client):
    answer = next(item for item in client.app.state.repository.records("answer") if item["estado"] == "respondida")
    sources = client.get("/queries", params={"q": answer["consulta"]}).text.split('aria-label="Fuentes"')[1]
    assert not re.search(r"<span>[A-Z]+-?[0-9a-zA-Z.-]{6,}</span>", sources)


def test_evidence_card_has_accented_labels_one_date_and_no_repeated_title(client):
    html = client.get("/evidence/N-2cf673d2b74a").text
    assert "Fecha publicacion" not in html and "Titulo" not in html
    assert html.split("<main")[1].count("El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún") == 2  # h1 + card title
    assert "2026-10-05T14:00:00Z" not in html and html.count("05/10/2026") == 1
    assert "Descripción" in html and re.search(r'<a class="link link--external"[^>]*>\s*Abrir fuente original', html)
    assert 'data-history-back' in html


def test_evidence_api_labels_its_fields_and_formats_the_date(client):
    body = client.get("/api/evidence/N-2cf673d2b74a").json()
    assert body["etiquetas"]["titulo"] == "Título" and body["etiquetas"]["descripcion"] == "Descripción"
    assert body["fecha_texto"] == "05/10/2026 09:00"
    assert body["campos"]["descripcion"]


@pytest.mark.parametrize("path, has_drawer", [
    ("/cases/CASO-001", True), ("/groups/G-001", True), ("/groups/G-001/context", True),
    ("/groups/G-003/context", False), ("/cases/CASO-001/review", False), ("/cases/CASO-001/draft", False),
])
def test_source_drawer_only_where_there_are_citations(client, path, has_drawer):
    assert ('id="source-panel"' in client.get(path).text) is has_drawer


def test_closed_drawer_is_inert_and_labelled_for_screen_readers(client):
    drawer = client.get("/cases/CASO-001").text.split('id="source-panel"')[1].split(">")[0]
    assert "inert" in drawer and 'aria-label="Fuente"' in client.get("/cases/CASO-001").text


def test_offline_instance_says_so_in_every_header(client, tmp_path):
    assert 'class="offline-flag"' in client.get("/inbox").text
    with TestClient(create_app(Settings(database=tmp_path / "online.sqlite3", offline=False, gemini_api_key="k"))) as online:
        assert 'class="offline-flag"' not in online.get("/inbox").text


def test_disabled_case_file_button_points_to_its_reason(client):
    html = client.get("/groups/G-007").text
    button = re.search(r"<button[^>]*>Generar ficha</button>", html).group(0)
    assert "disabled" in button and 'aria-describedby="generator-hint"' in button and 'id="generator-hint"' in html
    assert "Sin conexión: " in html and "Sin conexión:" in html.split('id="generator-hint"')[1]


def test_visible_copy_uses_one_term_per_concept(client):
    for path in ("/cases/CASO-001", "/cases/CASO-001/draft", "/cases/CASO-001/review", "/inbox"):
        html = client.get(path).text
        visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", visible)
        assert "Paquete editorial" not in visible and "paquete editorial" not in visible, path
        assert not re.search(r"\b[Cc]aso\b", visible), path


def test_justifications_use_decimal_commas_in_popover_and_methodology(client):
    from whoami.backend.reports import spanish_decimals

    assert spanish_decimals("Base 0.6 por el tema; similitud 0.59, versión 2025-10.") == "Base 0,6 por el tema; similitud 0,59, versión 2025-10."
    assert not re.search(r"\d\.\d", client.get("/methodology").text.split('class="calc"')[1].split("</table>")[0])


def test_api_title_names_the_product_correctly(client):
    assert client.app.title == "TVN DeepMind AI"


def reviewer_field(html):
    return re.search(r'<input name="actor"[^>]*value="([^"]*)"', html).group(1)


def decide(client, name, version=None):
    case = client.app.state.repository.case("CASO-001")
    state = "descartado" if case["estado_revision"] != "descartado" else "en_revision"
    return client.post("/cases/CASO-001/review", data={"state": state, "actor": name, "note": "Verificar fuentes",
                                                      "expected_version": version or case["version"]})


def test_the_reviewer_stays_in_the_form_right_after_a_decision(client):
    first = decide(client, "Ana Pérez")
    assert first.status_code == 200 and reviewer_field(first.text) == "Ana Pérez"
    changed = decide(client, "Luis Mora")
    assert changed.status_code == 200 and reviewer_field(changed.text) == "Luis Mora"
    assert reviewer_field(client.get("/cases/CASO-001/review").text) == "Luis Mora"


def test_a_rejected_decision_keeps_the_entered_reviewer(client):
    rejected = decide(client, "Ana Pérez", 999)
    assert rejected.status_code == 409 and reviewer_field(rejected.text) == "Ana Pérez"
