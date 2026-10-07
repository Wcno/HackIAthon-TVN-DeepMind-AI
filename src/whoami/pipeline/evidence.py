"""Everything citable: news items, World Bank indicators, INEC series points and earthquakes as `Evidence`.

Same shape as the synthetic set in `demo.py`, generalized to every row of the processed files. Figures use the
Spanish decimal comma, and a null value stays an empty string, never `"0"`.
"""

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from whoami.contracts import EVENTS_GEOJSON, INDICATORS_CSV, INEC_CSV, NEWS_CSV
from whoami.schemas import Evidence, parse_utc

WB_LABELS = {
    "NY.GDP.MKTP.KD.ZG": "Crecimiento del PIB",
    "FP.CPI.TOTL.ZG": "Inflación, precios al consumidor",
    "SL.UEM.TOTL.ZS": "Desempleo",
    "NE.EXP.GNFS.ZS": "Exportaciones de bienes y servicios",
    "IT.NET.USER.ZS": "Usuarios de internet",
    "SP.POP.TOTL": "Población total",
}


def spanish_number(value: float | str, decimals: int = 2) -> str:
    """Spanish decimal comma; a null (empty cell) stays empty so it is never read as zero."""
    if value == "":
        return ""
    return f"{float(value):.{decimals}f}".replace(".", ",")


def news_evidence(row: dict) -> Evidence:
    fields = {"titulo": row["titulo"], "medio": row["medio"], "fecha_publicacion": row["fecha_publicacion"]}
    if row.get("descripcion"):
        fields["descripcion"] = row["descripcion"]
    return Evidence(
        id_evidencia=row["id_noticia"],
        tipo="noticia",
        titulo=row["titulo"],
        url=row["url"],
        fecha=parse_utc(row["fecha_publicacion"]),
        campos=fields,
    )


def indicator_evidence(row: dict) -> Evidence:
    country, indicator, year = row["pais_iso3"], row["indicador_id"], row["anio"]
    label = WB_LABELS[indicator]
    return Evidence(
        id_evidencia=f"WB-{country}-{indicator}-{year}",
        tipo="indicador",
        titulo=f"{label} ({country}, {year})",
        url=row["fuente_url"],
        fecha=None,
        campos={"indicador": label, "periodo": year, "valor": spanish_number(row["valor"]), "unidad": row["unidad"]},
    )


def inec_evidence(row: dict) -> Evidence:
    return Evidence(
        id_evidencia=f"INEC-{row['serie_id']}-{row['periodo']}",
        tipo="serie_inec",
        titulo=f"{row['serie']} ({row['periodo']})",
        url=row["fuente_url"],
        fecha=None,
        campos={
            "serie": row["serie"],
            "periodo": row["periodo"],
            "valor": spanish_number(row["valor"]),
            "unidad": row["unidad"],
            "base": row["base"],
            "frecuencia": row["frecuencia"],
        },
    )


def quake_evidence(props: dict) -> Evidence:
    return Evidence(
        id_evidencia=f"USGS-{props['id']}",
        tipo="sismo",
        titulo=f"Sismo {props['place']}",
        url=props["url"],
        fecha=parse_utc(props["time"]),
        campos={
            "lugar": props["place"],
            "periodo": props["time"][:10],
            "valor": spanish_number(props["magnitude"], 1),
            "unidad": "magnitud",
            "hora_utc": props["time"],
            "estado": props["status"],
        },
    )


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def load_news_rows() -> list[dict]:
    return _read_csv(NEWS_CSV)


def _quake_properties() -> Iterable[dict]:
    with EVENTS_GEOJSON.open(encoding="utf-8") as file:
        return [feature["properties"] for feature in json.load(file)["features"]]


def load_official_evidence() -> dict[str, Evidence]:
    """Every row of the three official files, every country."""
    evidences = [indicator_evidence(row) for row in _read_csv(INDICATORS_CSV)]
    evidences += [inec_evidence(row) for row in _read_csv(INEC_CSV)]
    evidences += [quake_evidence(props) for props in _quake_properties()]
    return {evidence.id_evidencia: evidence for evidence in evidences}
