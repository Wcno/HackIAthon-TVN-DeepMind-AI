"""G6: the "Generar ficha" button builds the case file of one group live, through the batch generation path."""

import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.pipeline import load_pipeline
from whoami.backend.repository import EditorialRepository
from whoami.backend.settings import Settings
from whoami.contracts import DEMO

HTMX = {"HX-Request": "true", "HX-Target": "desk"}
SOURCE = "N-5a85a8d35030"
GROUNDED = {"afirmaciones": [{
    "texto": "El Servicio Geológico de EE. UU. reportó el sismo frente a Burica.", "tipo": "hecho", "atribuida_a": None,
    "citas": [{"id_evidencia": SOURCE, "campo": "descripcion",
               "pasaje": "El Servicio Geológico de EE. UU. reportó el sismo frente a las costas de Burica."}]}]}
INVENTED = {"afirmaciones": [{
    "texto": "El sismo dejó tres heridos.", "tipo": "hecho", "atribuida_a": None,
    "citas": [{"id_evidencia": SOURCE, "campo": "descripcion", "pasaje": "El sismo dejó tres heridos en Burica."}]}]}
HEADLINE_ONLY = {"afirmaciones": [{
    "texto": "TVN estrena nueva temporada.", "tipo": "hecho", "atribuida_a": None,
    "citas": [{"id_evidencia": "N-414e1be5622c", "campo": "titulo", "pasaje": "estrena nueva temporada"}]}]}
PACKAGE = {
    "titulo": "Sismo frente a Burica", "brief": "El USGS reportó un sismo frente a Burica.",
    "enfoque_interes_publico": "Seguridad de la zona fronteriza.", "preguntas": ["¿Hubo daños?", "¿Hubo réplicas?", "¿Qué dice Sinaproc?"],
    "fuentes_y_verificaciones": ["Confirmar con el catálogo USGS."], "guion": "El USGS reportó un sismo frente a Burica.",
    "copy_digital": "Sismo frente a Burica.",
}
PARTIAL_GROUP, INSUFFICIENT_GROUP = "G-006", "G-007"


class Provider:
    """Answers Gemini by the purpose of the call (the name of its JSON schema) and keeps what was asked."""

    def __init__(self, replies, status=200):
        self.replies, self.status, self.purposes = replies, status, []

    def __call__(self, request):
        purpose = json.loads(request.content)["response_format"]["json_schema"]["name"]
        self.purposes.append(purpose)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "boom"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(self.replies[purpose])}}]})


def app_with(tmp_path, provider, *, offline=False):
    settings = Settings(database=tmp_path / "db.sqlite3", offline=offline, gemini_api_key="" if offline else "test-secret",
                        generation_attempts=1)
    return TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider)))


def generate(client, group_id=PARTIAL_GROUP, **kwargs):
    return client.post(f"/groups/{group_id}/case-file", **kwargs)


def has_tabs(html):
    return all(f">{tab}</a>" in html for tab in ("Historia", "Borrador", "Revisión"))


def test_a_group_without_case_file_offers_the_button_online(tmp_path):
    with app_with(tmp_path, Provider({})) as client:
        html = client.get(f"/groups/{PARTIAL_GROUP}").text
    assert f'hx-post="/groups/{PARTIAL_GROUP}/case-file"' in html
    assert "Generar ficha" in html and "disabled" not in html.split("Generar ficha")[0].rsplit("<button", 1)[1]
    assert not has_tabs(html)


def test_offline_the_button_is_disabled_with_the_reason(tmp_path):
    with app_with(tmp_path, Provider({}), offline=True) as client:
        html = client.get(f"/groups/{PARTIAL_GROUP}").text
    button = html.split("Generar ficha")[0].rsplit("<button", 1)[1]
    assert "disabled" in button
    assert "Sin conexión" in html and "Gemini" in html


def test_offline_generation_is_refused_without_calling_gemini(tmp_path):
    provider = Provider({})
    with app_with(tmp_path, provider, offline=True) as client:
        response = generate(client, headers=HTMX)
        assert response.status_code == 409 and "Sin conexión" in response.text
        assert provider.purposes == []
        assert client.app.state.editorial.group(PARTIAL_GROUP)["id_caso"] is None


def test_generating_creates_the_case_file_and_opens_it_with_its_tabs(tmp_path):
    provider = Provider({"afirmaciones": GROUNDED, "paquete": PACKAGE})
    with app_with(tmp_path, provider) as client:
        response = generate(client, headers=HTMX)
        assert response.status_code == 200
        assert provider.purposes == ["afirmaciones", "paquete"]
        case_id = client.app.state.editorial.group(PARTIAL_GROUP)["id_caso"]
        assert case_id == "CASO-006" and response.headers["HX-Push-Url"] == f"/cases/{case_id}"
        assert has_tabs(response.text) and "El Servicio Geológico de EE. UU. reportó el sismo" in response.text
        case = client.app.state.repository.case(case_id)
        assert case["borrador"]["titulo"] == "Sismo frente a Burica" and case["estado_revision"] == "nuevo"
        assert has_tabs(client.get(f"/groups/{PARTIAL_GROUP}").text)
        assert "Generar ficha" not in client.get(f"/groups/{PARTIAL_GROUP}").text


def test_the_generated_case_file_survives_a_restart(tmp_path):
    with app_with(tmp_path, Provider({"afirmaciones": GROUNDED, "paquete": PACKAGE})) as client:
        generate(client, headers=HTMX)
    with app_with(tmp_path, Provider({}), offline=True) as client:
        assert client.app.state.editorial.group(PARTIAL_GROUP)["id_caso"] == "CASO-006"
        assert client.app.state.repository.case("CASO-006")["version"] == 1
        assert client.get("/cases/CASO-006/draft").status_code == 200


def test_without_javascript_the_post_redirects_to_the_new_case_file(tmp_path):
    with app_with(tmp_path, Provider({"afirmaciones": GROUNDED, "paquete": PACKAGE})) as client:
        response = generate(client, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/cases/CASO-006"


def test_a_group_that_already_has_a_case_file_is_opened_without_calling_gemini(tmp_path):
    provider = Provider({})
    with app_with(tmp_path, provider) as client:
        response = generate(client, "G-001", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/cases/CASO-001"
    assert provider.purposes == []


def test_a_provider_failure_leaves_a_retry_not_a_dead_end(tmp_path):
    failing = Provider({}, status=500)
    with app_with(tmp_path, failing) as client:
        response = generate(client, headers=HTMX)
        assert response.status_code == 503
        assert "No se pudo generar la ficha" in response.text and "Reintentar" in response.text
        assert response.headers["HX-Retarget"] == "#case-file-generator"
        assert client.app.state.editorial.group(PARTIAL_GROUP)["id_caso"] is None
    working = Provider({"afirmaciones": GROUNDED, "paquete": PACKAGE})
    with app_with(tmp_path, working) as client:
        assert generate(client, headers=HTMX).status_code == 200


def test_claims_the_sources_do_not_back_end_honestly_without_a_case_file(tmp_path):
    with app_with(tmp_path, Provider({"afirmaciones": INVENTED})) as client:
        response = generate(client, headers=HTMX)
        assert response.status_code == 422
        assert "ninguna afirmación" in response.text and "Reintentar" not in response.text
        assert client.app.state.editorial.group(PARTIAL_GROUP)["id_caso"] is None


def test_an_insufficient_group_gets_a_case_file_without_draft_and_says_so(tmp_path):
    provider = Provider({"afirmaciones": HEADLINE_ONLY})
    with app_with(tmp_path, provider) as client:
        response = generate(client, INSUFFICIENT_GROUP, headers=HTMX)
        assert response.status_code == 200 and provider.purposes == ["afirmaciones"]
        case = client.app.state.repository.case("CASO-007")
        assert case["borrador"] is None and case["estado_evidencia"] == "insuficiente"
        assert "Evidencia insuficiente" in response.text and "Buscar más fuentes" in response.text


def test_a_generated_case_file_is_kept_by_the_repository_across_imports(tmp_path):
    bundle = load_pipeline(DEMO, DEMO)
    generated = next(case for case in bundle.cases if case["id_caso"] == "CASO-005")
    without = replace(
        bundle, cases=tuple(c for c in bundle.cases if c is not generated),
        groups=tuple(g | {"id_caso": None} if g["id_grupo"] == generated["id_grupo"] else g for g in bundle.groups))
    repository = EditorialRepository(tmp_path / "db.sqlite3")
    repository.import_bundle(without)
    repository.add_generated_case(generated)
    assert repository.add_generated_case(generated) == "CASO-005"  # idempotent per group
    repository.import_bundle(without)
    assert repository.case("CASO-005")["version"] == 1
    assert repository.record("group", generated["id_grupo"])["id_caso"] == "CASO-005"
    repository.import_bundle(bundle)  # the committed bundle now ships the group's case file and wins
    assert repository.case("CASO-005")["version"] == 1
    repository.import_bundle(without)
    assert repository.record("group", generated["id_grupo"])["id_caso"] is None


@pytest.mark.parametrize("path", ["/groups/G-006", "/groups/G-007"])
def test_the_pending_panel_does_not_contradict_the_evidence_badge(tmp_path, path):
    with app_with(tmp_path, Provider({})) as client:
        html = client.get(path).text.split('id="case"')[1]
    assert "Sin ficha" in html and "Este tema aún no tiene ficha de evidencia" not in html
    assert "Nuevo</span>" not in html.split("case__badges")[1].split("</div>")[0]
