"""G6 quality and methodology screens: every figure comes from the data files and the contract."""

import csv
import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.reports import methodology_view, quality_view
from whoami.backend.settings import Settings
from whoami.contracts import PROCESSED, RULES_VERSION, SCORE_WEIGHTS


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        yield client


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def load(name: str) -> dict:
    return json.loads((PROCESSED / name).read_text(encoding="utf-8"))


def spanish(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def test_news_counts_come_from_the_quality_report_with_thousands_dots(client):
    news = load("calidad_noticias.json")
    page = text_of(client.get("/quality").text)
    for value in (news["registros_leidos"], news["noticias_unicas"], news["incluidas"], sum(news["excluidas_por_motivo"].values())):
        assert spanish(value) in page
    assert "30.823" in page
    assert f"{spanish(news['registros_leidos'] - news['noticias_unicas'])} repetidas" in page


def test_excluded_rows_are_listed_by_reason(client):
    news = load("calidad_noticias.json")
    page = client.get("/quality").text
    for reason, count in news["excluidas_por_motivo"].items():
        assert reason.replace("fuera_de_ventana", "fuera de la ventana") in page and reason not in page and spanish(count) in page
    inec = load("calidad_inec.json")
    for item in inec["excluidos"]:
        assert item["periodo"] in page
    assert "Excluido: mes sin publicar." in page and "Excluido: período duplicado." in page


def test_kept_nulls_are_labelled_and_shown_empty(client):
    inec = load("calidad_inec.json")
    page = text_of(client.get("/quality").text)
    assert "Nulos conservados" in page
    assert f"Nulos conservados {inec['filas_nulas']}" in page
    nulled = [period for series in inec["series"].values() for period in series["nulos"]]
    assert nulled and all(period in page for period in nulled)


def test_snapshot_provenance_and_hashes_come_from_the_manifest(client):
    manifest = json.loads((PROCESSED.parent / "manifest.json").read_text(encoding="utf-8"))
    page = text_of(client.get("/quality").text)
    assert manifest["version"] in page
    assert f"{len(manifest['consultas'])} descargas registradas" in page
    for digest in manifest["sha256"].values():
        assert digest in page
    assert "Integridad: verificada" in page and "verified" not in page
    assert "6 oct, 22:32 a 23:00" in page  # TVN downloads, shown in Panama time (UTC-5)


def test_cutoff_is_shown_in_panama_time(client):
    assert "7 oct 2026, 19:51" in text_of(client.get("/quality").text)


@pytest.fixture
def small_snapshot(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    news = {
        "ventana": {"desde": "2026-10-01T03:00:00Z", "hasta": "2026-10-04T03:00:00Z"},
        "registros_leidos": 10, "noticias_unicas": 9, "incluidas": 4, "excluidas_por_motivo": {"fuera_de_ventana": 5},
        "cobertura_por_fuente": {"tvn": {"incluidas": 4, "desde": "2026-10-02T04:30:00Z", "hasta": "2026-10-03T23:30:00Z", "dias_con_noticias": 2}},
        "incluidas_por_origen_fecha": {"feed": 4},
    }
    (processed / "calidad_noticias.json").write_text(json.dumps(news), encoding="utf-8")
    sources = [{"id_fuente": "tvn", "medio": "TVN", "dominio": "www.tvn-2.com", "tipo": "medio", "canales": [{"canal": "rss", "url": "https://www.tvn-2.com/rss/"}],
                "licencia": "Sin licencia", "condiciones_reutilizacion": "Solo metadatos."}]
    (processed / "fuentes.json").write_text(json.dumps({"fuentes": sources}), encoding="utf-8")
    with (processed / "noticias.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["id_fuente", "fecha_publicacion", "fecha_deteccion"])
        writer.writeheader()
        # 04:30Z is still Oct 1 in Panama (23:30 local); 23:30Z is Oct 3 in Panama; 03:30Z on the 4th is Oct 3 local.
        for published in ("2026-10-02T04:30:00Z", "2026-10-02T15:00:00Z", "2026-10-03T23:30:00Z", "2026-10-04T03:30:00Z"):
            writer.writerow({"id_fuente": "tvn", "fecha_publicacion": published, "fecha_deteccion": ""})
    return processed


def test_day_strip_buckets_by_panama_day_not_utc(small_snapshot):
    coverage = quality_view(small_snapshot)["news"]["coverage"]
    source = coverage["groups"][0]["sources"][0]
    assert (coverage["first"], coverage["last"]) == ("30 sep", "3 oct")
    # Panama days: Sep 30 (window start local), Oct 1, Oct 2, Oct 3. 04:30Z on Oct 2 is Oct 1 local.
    assert source["days"] == [False, True, True, True]
    assert source["active"] == 3 and source["total"] == 4
    assert "3 de 4 días con noticias" in source["range"] and "1 oct, 23:30" in source["range"]


def test_missing_reports_degrade_to_a_notice(tmp_path):
    view = quality_view(tmp_path)
    assert view["news"] is None and view["snapshot"] is None and view["provenance"] == []


def test_methodology_weights_ranges_and_rules_version_come_from_the_contract(client):
    page = client.get("/methodology").text
    text = text_of(page)
    for key, weight in SCORE_WEIGHTS.items():
        assert f'<span class="pop__key pop__key--{key}">{key}</span>' in page
        assert f"{weight} <small>pts</small>" in page
        assert f"width:{weight}%" in page
    assert "P igual a 30 R más 25 I más 20 U más 15 N más 10 E" in page
    assert f"Versión de las reglas: {RULES_VERSION}" in text
    assert "Bajo: de 0 a menos de 40" in text and "Alto: de 70 a 100" in text


def test_worked_example_matches_the_group_score(client):
    group = client.app.state.editorial.inbox(include_covered=True)[0]
    score = group["puntaje"]
    page = client.get("/methodology").text
    text = text_of(page)
    assert group["titulo"] in text
    expected_total = f"{score['valor']:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    assert f'<p class="example__total"><b>{expected_total}</b>' in page
    points = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        points += score["componentes"][key] * weight
        assert score["justificaciones"][key] in text
    assert points == pytest.approx(score["valor"])
    assert f"Rango {score['rango']}" in text and f"Reglas {score['version_reglas']}" in text


def test_grupo_query_switches_the_example(client):
    ranked = client.app.state.editorial.inbox(include_covered=True)
    other = ranked[-1]
    assert other["id_grupo"] != ranked[0]["id_grupo"]
    page = client.get("/methodology", params={"grupo": other["id_grupo"]}).text
    assert f'<p class="example__title">{other["titulo"]}</p>' in page
    assert f'value="{other["id_grupo"]}" selected' in page
    assert f'<p class="example__title">{ranked[0]["titulo"]}</p>' not in page


def test_example_selector_is_a_get_form_with_htmx_swap_and_unknown_group_falls_back(client):
    page = client.get("/methodology").text
    assert 'method="get"' in page and 'name="grupo"' in page and 'hx-get="/methodology"' in page and 'hx-select="#ejemplo"' in page
    ranked = client.app.state.editorial.inbox(include_covered=True)
    assert f'<p class="example__title">{ranked[0]["titulo"]}</p>' in client.get("/methodology", params={"grupo": "nope"}).text
    fragment = client.get("/methodology", params={"grupo": ranked[-1]["id_grupo"]}, headers={"HX-Request": "true"}).text
    assert "<html" not in fragment and 'id="ejemplo"' in fragment


def test_synthetic_notice_stays_on_the_example_only(client):
    methodology = client.get("/methodology").text
    assert "El ejemplo usa datos sintéticos de demostración" in methodology
    assert "El ejemplo usa datos sintéticos" not in client.get("/quality").text


def test_ai_versus_baseline_is_an_empty_slot_without_numbers(client):
    page = client.get("/methodology").text
    section = page[page.index('id="evaluacion"'):]
    text = text_of(section)
    assert "Pendiente de G7" in text and "Sin resultados todavía" in text
    assert not re.findall(r"\d", re.sub(r"G7", "", text))


def test_methodology_view_without_groups_has_no_example():
    assert methodology_view([])["example"] is None


def test_panama_day_helper_is_not_utc():
    from whoami.backend.reports import panama

    assert panama("2026-10-02T04:30:00Z").date() == date(2026, 10, 1)
