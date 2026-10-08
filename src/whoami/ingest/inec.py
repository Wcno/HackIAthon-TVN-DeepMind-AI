"""INEC Panama (§6.B): monthly CPI and quarterly GDP headline series, built into `indicadores_inec.csv`.

INEC files are not UTF-8 and their layout changes by publication, so the download links are discovered
from the catalog pages and the parsers read cells by their header codes, never by position alone.
"""

import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import quote, urljoin
from xml.etree import ElementTree

from whoami.contracts import INEC_COLUMNS, INEC_CSV, INEC_FROM_YEAR, INEC_QUALITY_JSON, PROCESSED, RAW
from whoami.ingest import http
from whoami.ingest.output import iso, write_csv, write_json
from whoami.ingest.raw import RawFile, RawStore

SITE: Final = "https://www.inec.gob.pa/"
CPI_CATALOG: Final = SITE + "avance/Default2.aspx?ID_CATEGORIA=2&ID_CIFRAS=10&ID_IDIOMA=1"
GDP_CATALOG: Final = SITE + "publicaciones/Default3.aspx?ID_CATEGORIA=4&ID_PUBLICACION=1419&ID_SUBCATEGORIA=73"
LICENSE: Final = "CC BY 4.0 - Instituto Nacional de Estadística y Censo (INEC), Contraloría General de la República de Panamá"

STORE: Final = RawStore(RAW / "inec")
CPI_FILE: Final = "ipc_anexo4.xlsx"
GDP_FILE: Final = "pib_trimestral.csv"

#: (catalog page, raw name of the catalog page, pattern of the data link inside it, raw name of the data file)
DOWNLOADS: Final = (
    (CPI_CATALOG, "catalogo_ipc.html", r"archivos/[^\"']*Anexo 4\.xlsx", CPI_FILE),
    (GDP_CATALOG, "catalogo_pib.html", r"archivos/[^\"']*PIB_TRIMESTRAL2018\.csv", GDP_FILE),
)

CSV_ENCODING: Final = "cp850"
DUPLICATE_PERIOD: Final = "periodo_duplicado"
REPEATED_LABEL: Final = "etiqueta repetida en la fuente, se conserva la primera aparición"
UNPUBLISHED: Final = "mes_sin_publicar"

MONTHS: Final = {
    name: number
    for number, name in enumerate(
        ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
        start=1,
    )
}

CPI_NAME: Final = "Índice de precios al consumidor, nacional urbano"
GDP_NAME: Final = "Producto interno bruto trimestral"


@dataclass(frozen=True)
class Series:
    name: str
    frequency: str
    unit: str
    base: str


SERIES: Final = {
    "ipc_indice": Series(CPI_NAME, "mensual", "índice", "2024=100"),
    "ipc_var_mensual": Series(f"{CPI_NAME}, variación mensual", "mensual", "% mensual", "2024=100"),
    "ipc_var_interanual": Series(f"{CPI_NAME}, variación interanual", "mensual", "% interanual", "2024=100"),
    "pib_constante": Series(f"{GDP_NAME}, precios constantes", "trimestral", "millones de balboas", "2018"),
    "pib_corriente": Series(f"{GDP_NAME}, precios corrientes", "trimestral", "millones de balboas", ""),
    "pib_constante_var_interanual": Series(
        f"{GDP_NAME}, precios constantes, variación interanual (calculada)", "trimestral", "% interanual", "2018"
    ),
}

CPI_COLUMNS: Final = {"B": "ipc_indice", "C": "ipc_var_mensual", "D": "ipc_var_interanual"}
GDP_GROUPS: Final = {"PIBCONSTANTE": "pib_constante", "PIBCORRIENTE": "pib_corriente"}


@dataclass(frozen=True)
class Observation:
    serie_id: str
    period: str
    value: float | None
    source: RawFile


def fetch() -> list[str]:
    """Returns the files that failed."""
    failures = []
    for catalog, catalog_name, link_pattern, name in DOWNLOADS:
        print(f"  inec/{name} ...", flush=True)
        try:
            page = http.get(catalog)
            STORE.save(catalog_name, page)
            STORE.save(name, http.get(find_link(page.body, link_pattern)))
        except Exception as error:
            print(f"  inec/{name} FAILED: {type(error).__name__}: {error}")
            failures.append(name)
    return failures


def build() -> dict:
    files = {file.name: file for file in STORE.files()}
    cpi, cpi_excluded = parse_cpi(files[CPI_FILE].read(), files[CPI_FILE])
    gdp, gdp_excluded = parse_gdp(files[GDP_FILE].read().decode(CSV_ENCODING), files[GDP_FILE])
    observations = [
        observation
        for observation in cpi + gdp + year_on_year(gdp)
        if int(observation.period[:4]) >= INEC_FROM_YEAR
    ]
    observations.sort(key=lambda observation: (list(SERIES).index(observation.serie_id), observation.period))

    PROCESSED.mkdir(parents=True, exist_ok=True)
    write_csv(INEC_CSV, INEC_COLUMNS, (_row(observation) for observation in observations))
    report = quality_report(observations, cpi_excluded + gdp_excluded)
    write_json(INEC_QUALITY_JSON, report)
    return report


def find_link(catalog_html: bytes, pattern: str) -> str:
    match = re.search(pattern, catalog_html.decode("latin-1"))
    if not match:
        raise LookupError(f"no link matching {pattern!r} in the catalog page")
    return urljoin(SITE, quote(match.group(), safe="/"))


def parse_number(text: str) -> float | None:
    """Accepts `1234.5`, `1,234.5`, `1.234,5` and `12,5`; INEC dashes and dots mean no value."""
    cleaned = text.strip()
    if not cleaned or cleaned in {"-", "..", "..."}:
        return None
    if "," in cleaned and "." in cleaned:
        decimal = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        cleaned = cleaned.replace(thousands, "").replace(decimal, ".")
    elif cleaned.count(",") > 1 or re.fullmatch(r"-?\d{1,3},\d{3}", cleaned):
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def parse_gdp(text: str, source: RawFile) -> tuple[list[Observation], list[dict]]:
    """Three header rows: aggregate group, activity code, label. Only the total GDP column of each group is read."""
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    groups, codes = rows[0], rows[1]
    columns = {
        GDP_GROUPS[group.strip()]: index
        for index, (group, code) in enumerate(zip(groups, codes, strict=False))
        if group.strip() in GDP_GROUPS and code.strip() == "PIB"
    }
    observations, excluded, seen = [], [], set()
    for row in rows[2:]:
        match = re.fullmatch(r"(\d{4})-Q([1-4])", row[0].strip()) if row else None
        if not match:
            continue
        period = f"{match[1]}-T{match[2]}"
        if period in seen:
            excluded.append({"serie_id": "pib", "periodo": period, "motivo": DUPLICATE_PERIOD, "detalle": REPEATED_LABEL})
            continue
        seen.add(period)
        observations += [
            Observation(serie_id, period, parse_number(row[index]), source) for serie_id, index in columns.items()
        ]
    return observations, excluded


def year_on_year(gdp: list[Observation]) -> list[Observation]:
    """Null when the same quarter of the previous year is not available."""
    levels = {observation.period: observation.value for observation in gdp if observation.serie_id == "pib_constante"}
    growth = []
    for period, value in levels.items():
        previous = levels.get(f"{int(period[:4]) - 1}{period[4:]}")
        change = None if value is None or not previous else round((value / previous - 1) * 100, 4)
        source = next(o.source for o in gdp if o.period == period)
        growth.append(Observation("pib_constante_var_interanual", period, change, source))
    return growth


def parse_cpi(xlsx: bytes, source: RawFile) -> tuple[list[Observation], list[dict]]:
    """Year rows (annual average) set the year; month rows hold index, monthly and year-on-year change."""
    observations, excluded, year = [], [], None
    for cells in _sheet_rows(xlsx):
        label = cells.get("A", "").strip()
        if re.fullmatch(r"\d{4}", label):
            year = int(label)
        elif label.lower() in MONTHS and year:
            period = f"{year}-{MONTHS[label.lower()]:02d}"
            if not any(column in cells for column in CPI_COLUMNS):
                excluded.append({"serie_id": "ipc", "periodo": period, "motivo": UNPUBLISHED})
                continue
            observations += [
                Observation(serie_id, period, parse_number(cells.get(column, "")), source)
                for column, serie_id in CPI_COLUMNS.items()
            ]
    return observations, excluded


def quality_report(observations: list[Observation], excluded: list[dict]) -> dict:
    by_series = {
        serie_id: [observation for observation in observations if observation.serie_id == serie_id] for serie_id in SERIES
    }
    return {
        "filas": len(observations),
        "filas_con_valor": sum(observation.value is not None for observation in observations),
        "filas_nulas": sum(observation.value is None for observation in observations),
        "anio_inicial": INEC_FROM_YEAR,
        "series": {
            serie_id: {
                "filas": len(rows),
                "desde": rows[0].period if rows else None,
                "hasta": rows[-1].period if rows else None,
                "nulos": [row.period for row in rows if row.value is None],
            }
            for serie_id, rows in by_series.items()
        },
        "excluidos_por_motivo": dict(Counter(item["motivo"] for item in excluded).most_common()),
        "excluidos": excluded,
    }


def _sheet_rows(xlsx: bytes) -> list[dict[str, str]]:
    """First worksheet as `{column letter: text}` per row, resolving shared strings. Empty cells are absent."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(xlsx)) as archive:
        strings = [
            "".join(text.text or "" for text in item.iter(f"{namespace}t"))
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).iter(f"{namespace}si")
        ]
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(f"{namespace}row"):
        cells = {}
        for cell in row.iter(f"{namespace}c"):
            value = cell.find(f"{namespace}v")
            if value is not None:
                cells[re.match(r"[A-Z]+", cell.get("r"))[0]] = strings[int(value.text)] if cell.get("t") == "s" else value.text
        rows.append(cells)
    return rows


def _row(observation: Observation) -> dict:
    series = SERIES[observation.serie_id]
    return {
        "serie_id": observation.serie_id,
        "serie": series.name,
        "periodo": observation.period,
        "frecuencia": series.frequency,
        "valor": "" if observation.value is None else observation.value,
        "unidad": series.unit,
        "base": series.base,
        "fuente_url": observation.source.url,
        "fecha_extraccion": iso(observation.source.fetched_at),
        "licencia": LICENSE,
    }
