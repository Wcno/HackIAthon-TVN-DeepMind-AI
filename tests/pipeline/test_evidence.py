from datetime import UTC, datetime

from whoami.pipeline.evidence import (
    WB_LABELS,
    indicator_evidence,
    inec_evidence,
    load_news_rows,
    load_official_evidence,
    news_evidence,
    quake_evidence,
)

NEWS_ROW = {
    "id_noticia": "N-abc123",
    "titulo": "El Canal de Panamá reduce tránsitos",
    "url": "https://example.test/canal",
    "medio": "TVN",
    "fecha_publicacion": "2026-10-05T14:00:00Z",
    "descripcion": "Limitará los tránsitos a 32 diarios.",
}


def test_news_evidence_keeps_title_outlet_date_and_description():
    evidence = news_evidence(NEWS_ROW)

    assert evidence.id_evidencia == "N-abc123"
    assert evidence.tipo == "noticia"
    assert evidence.fecha == datetime(2026, 10, 5, 14, tzinfo=UTC)
    assert evidence.campos == {
        "titulo": "El Canal de Panamá reduce tránsitos",
        "medio": "TVN",
        "fecha_publicacion": "2026-10-05T14:00:00Z",
        "descripcion": "Limitará los tránsitos a 32 diarios.",
    }


def test_news_evidence_omits_an_empty_description():
    evidence = news_evidence(NEWS_ROW | {"descripcion": ""})

    assert "descripcion" not in evidence.campos


WB_ROW = {
    "pais_iso3": "PAN",
    "indicador_id": "SL.UEM.TOTL.ZS",
    "anio": "2024",
    "valor": "8.451",
    "unidad": "% de la fuerza laboral",
    "fuente_url": "https://api.worldbank.org/x",
}


def test_indicator_evidence_uses_spanish_label_and_decimal_comma():
    evidence = indicator_evidence(WB_ROW)

    assert evidence.id_evidencia == "WB-PAN-SL.UEM.TOTL.ZS-2024"
    assert evidence.tipo == "indicador"
    assert evidence.titulo == "Desempleo (PAN, 2024)"
    assert evidence.campos == {
        "indicador": "Desempleo",
        "periodo": "2024",
        "valor": "8,45",
        "unidad": "% de la fuerza laboral",
    }


def test_a_null_indicator_value_is_empty_never_zero():
    evidence = indicator_evidence(WB_ROW | {"valor": ""})

    assert evidence.campos["valor"] == ""
    assert evidence.campos["periodo"] == "2024"
    assert evidence.campos["unidad"]


def test_every_world_bank_indicator_has_a_label():
    assert set(WB_LABELS) == {
        "NY.GDP.MKTP.KD.ZG",
        "FP.CPI.TOTL.ZG",
        "SL.UEM.TOTL.ZS",
        "NE.EXP.GNFS.ZS",
        "IT.NET.USER.ZS",
        "SP.POP.TOTL",
    }


INEC_ROW = {
    "serie_id": "ipc_var_interanual",
    "serie": "IPC, variación interanual",
    "periodo": "2026-08",
    "frecuencia": "mensual",
    "valor": "1.2345",
    "unidad": "% interanual",
    "base": "2024=100",
    "fuente_url": "https://www.inec.gob.pa/x.xlsx",
}


def test_inec_evidence_has_series_period_unit_base_and_frequency():
    evidence = inec_evidence(INEC_ROW)

    assert evidence.id_evidencia == "INEC-ipc_var_interanual-2026-08"
    assert evidence.tipo == "serie_inec"
    assert evidence.campos == {
        "serie": "IPC, variación interanual",
        "periodo": "2026-08",
        "valor": "1,23",
        "unidad": "% interanual",
        "base": "2024=100",
        "frecuencia": "mensual",
    }


def test_a_null_inec_value_is_empty_never_zero():
    assert inec_evidence(INEC_ROW | {"valor": ""}).campos["valor"] == ""


QUAKE = {
    "id": "us6000rerc",
    "magnitude": 4.5,
    "time": "2025-10-04T07:31:11Z",
    "status": "reviewed",
    "place": "195 km S of Burica, Panama",
    "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000rerc",
}


def test_quake_evidence_has_place_day_magnitude_and_utc_time():
    evidence = quake_evidence(QUAKE)

    assert evidence.id_evidencia == "USGS-us6000rerc"
    assert evidence.tipo == "sismo"
    assert evidence.fecha == datetime(2025, 10, 4, 7, 31, 11, tzinfo=UTC)
    assert evidence.campos["valor"] == "4,5"
    assert evidence.campos["unidad"] == "magnitud"
    assert evidence.campos["periodo"] == "2025-10-04"
    assert evidence.campos["hora_utc"] == "2025-10-04T07:31:11Z"


def test_quake_evidence_keeps_the_epicenter_when_the_catalog_gives_it():
    evidence = quake_evidence(QUAKE | {"latitude": 6.2706, "longitude": -82.7069})

    assert evidence.campos["latitud"] == "6.2706"
    assert evidence.campos["longitud"] == "-82.7069"
    assert "latitud" not in quake_evidence(QUAKE).campos


def test_the_processed_data_loads_as_citable_evidence():
    rows = load_news_rows()
    official = load_official_evidence()

    assert len(rows) > 1000
    assert {e.tipo for e in official.values()} == {"indicador", "serie_inec", "sismo"}
    assert "WB-CRI-SL.UEM.TOTL.ZS-2024" in official
    assert any(e.campos["valor"] == "" for e in official.values())
