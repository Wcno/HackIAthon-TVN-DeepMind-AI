"""World Bank indicators (§6.B): one query per indicator, built into the full country x indicator x year grid."""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from whoami.contracts import INDICATORS_COLUMNS, INDICATORS_CSV, INDICATORS_QUALITY_JSON, PROCESSED, RAW
from whoami.ingest import http
from whoami.ingest.output import iso, write_csv, write_json
from whoami.ingest.raw import RawFile, RawStore

API: Final = "https://api.worldbank.org/v2"
COUNTRIES: Final = ("PAN", "CRI", "COL", "DOM", "MEX", "GTM")
YEARS: Final = range(2010, 2025)
LICENSE: Final = "CC BY 4.0 - The World Bank (https://data.worldbank.org/summary-terms-of-use)"

#: The API returns `unit` empty, so the unit is derived from the indicator.
UNITS: Final = {
    "NY.GDP.MKTP.KD.ZG": "% anual",
    "FP.CPI.TOTL.ZG": "% anual",
    "SL.UEM.TOTL.ZS": "% de la fuerza laboral",
    "SP.POP.TOTL": "personas",
    "IT.NET.USER.ZS": "% de la poblacion",
    "NE.EXP.GNFS.ZS": "% del PIB",
}

STORE: Final = RawStore(RAW / "worldbank")


@dataclass(frozen=True)
class Observation:
    value: float | None
    source_url: str
    fetched_at: datetime


def fetch() -> list[str]:
    """Returns the indicators that failed."""
    failures = []
    for indicator in UNITS:
        print(f"  worldbank/{indicator} ...", flush=True)
        try:
            _fetch_indicator(indicator)
        except Exception as error:
            print(f"  worldbank/{indicator} FAILED: {type(error).__name__}: {error}")
            failures.append(indicator)
    return failures


def build() -> dict:
    observations = {}
    queries = {}
    for indicator in UNITS:
        queries[indicator] = _first_page(indicator)
        observations.update(_read_indicator(indicator))
    grid = [(country, indicator, year) for indicator in UNITS for country in COUNTRIES for year in YEARS]
    rows = [_row(key, observations.get(key), queries[key[1]]) for key in grid]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    write_csv(INDICATORS_CSV, INDICATORS_COLUMNS, rows)
    report = quality_report(grid, observations)
    write_json(INDICATORS_QUALITY_JSON, report)
    return report


def indicator_url(indicator: str, page: int = 1) -> str:
    return (
        f"{API}/country/{';'.join(COUNTRIES)}/indicator/{indicator}"
        f"?format=json&date={YEARS[0]}:{YEARS[-1]}&per_page=1000&page={page}"
    )


def parse_observations(payload: list, source_url: str, fetched_at: datetime) -> dict[tuple[str, str, int], Observation]:
    """`payload` is the API's `[meta, rows]`; rows outside the grid are ignored."""
    observations = {}
    for item in payload[1] or []:
        key = (item["countryiso3code"], item["indicator"]["id"], int(item["date"]))
        observations[key] = Observation(item["value"], source_url, fetched_at)
    return observations


def quality_report(grid: list[tuple[str, str, int]], observations: dict) -> dict:
    present = [key for key in grid if key in observations]
    missing = [key for key in grid if key not in observations]
    null_in_source = [key for key in present if observations[key].value is None]
    return {
        "filas_esperadas": len(grid),
        "filas_con_valor": len(present) - len(null_in_source),
        "filas_nulas_en_fuente": len(null_in_source),
        "filas_faltantes_agregadas": len(missing),
        "faltantes_por_indicador": dict(Counter(indicator for _, indicator, _ in missing).most_common()),
        "nulos_por_indicador": dict(Counter(indicator for _, indicator, _ in null_in_source).most_common()),
        "anios": {"desde": YEARS[0], "hasta": YEARS[-1]},
    }


def _fetch_indicator(indicator: str) -> None:
    page, pages = 1, 1
    while page <= pages:
        response = http.get(indicator_url(indicator, page))
        pages = json.loads(response.body)[0]["pages"]
        STORE.save(f"{indicator}_p{page}.json", response)
        page += 1


def _read_indicator(indicator: str) -> dict:
    observations = {}
    for file in STORE.files():
        if file.name.startswith(f"{indicator}_p"):
            observations |= parse_observations(json.loads(file.read()), file.url, file.fetched_at)
    return observations


def _first_page(indicator: str) -> RawFile:
    [first] = [file for file in STORE.files() if file.name == f"{indicator}_p1.json"]
    return first


def _row(key: tuple[str, str, int], observation: Observation | None, query: RawFile) -> dict:
    country, indicator, year = key
    return {
        "pais_iso3": country,
        "indicador_id": indicator,
        "anio": year,
        "valor": "" if observation is None or observation.value is None else observation.value,
        "unidad": UNITS[indicator],
        "fuente_url": observation.source_url if observation else query.url,
        "fecha_extraccion": iso(observation.fetched_at if observation else query.fetched_at),
        "licencia": LICENSE,
    }
