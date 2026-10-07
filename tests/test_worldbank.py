from datetime import UTC, datetime

from whoami.ingest import worldbank

FETCHED_AT = datetime(2026, 10, 7, tzinfo=UTC)
URL = "https://example.test/query"


def item(country: str, indicator: str, year: int, value: float | None) -> dict:
    return {"countryiso3code": country, "indicator": {"id": indicator}, "date": str(year), "value": value}


def test_parse_keeps_null_values_as_observations():
    payload = [{"pages": 1}, [item("PAN", "SP.POP.TOTL", 2020, None), item("PAN", "SP.POP.TOTL", 2021, 4.3)]]

    observations = worldbank.parse_observations(payload, URL, FETCHED_AT)

    assert observations[("PAN", "SP.POP.TOTL", 2020)].value is None
    assert observations[("PAN", "SP.POP.TOTL", 2021)].value == 4.3


def test_quality_report_separates_null_in_source_from_missing_combination():
    grid = [("PAN", "SP.POP.TOTL", 2020), ("PAN", "SP.POP.TOTL", 2021), ("CRI", "SP.POP.TOTL", 2020)]
    payload = [{}, [item("PAN", "SP.POP.TOTL", 2020, None), item("PAN", "SP.POP.TOTL", 2021, 4.3)]]
    observations = worldbank.parse_observations(payload, URL, FETCHED_AT)

    report = worldbank.quality_report(grid, observations)

    assert report["filas_con_valor"] == 1
    assert report["filas_nulas_en_fuente"] == 1
    assert report["filas_faltantes_agregadas"] == 1
    assert report["faltantes_por_indicador"] == {"SP.POP.TOTL": 1}


def test_row_for_missing_combination_has_empty_value_and_query_metadata():
    query = worldbank.RawFile("SP.POP.TOTL_p1.json", URL, "0" * 64, FETCHED_AT, path=None)

    row = worldbank._row(("CRI", "SP.POP.TOTL", 2020), None, query)

    assert row["valor"] == ""
    assert row["fuente_url"] == URL
    assert row["fecha_extraccion"] == "2026-10-07T00:00:00Z"
    assert row["unidad"] == "personas"


def test_every_indicator_has_a_unit():
    assert set(worldbank.UNITS) == {
        "NY.GDP.MKTP.KD.ZG",
        "FP.CPI.TOTL.ZG",
        "SL.UEM.TOTL.ZS",
        "SP.POP.TOTL",
        "IT.NET.USER.ZS",
        "NE.EXP.GNFS.ZS",
    }
    assert all(worldbank.UNITS.values())


def test_query_url_covers_all_countries_in_one_request():
    url = worldbank.indicator_url("SP.POP.TOTL")

    assert "PAN;CRI;COL;DOM;MEX;GTM" in url
    assert "date=2010:2024" in url
