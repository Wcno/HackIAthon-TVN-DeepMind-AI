"""Data contract shared by every subpackage: where processed files live and their columns (§7).

`ingest` writes these files and `ai` and `api` read them; nothing else couples them.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

#: Team decision D-04 (§6.A default): news from the 30 days before the extraction date.
NEWS_WINDOW: Final = timedelta(days=30)


def news_window_start(cutoff: datetime) -> datetime:
    return cutoff - NEWS_WINDOW


#: Team decision D-02: USGS events from this instant up to the extraction time.
EVENTS_WINDOW_START: Final = datetime(2025, 10, 2, tzinfo=UTC)

DATA: Final = Path(__file__).resolve().parents[2] / "data"
RAW: Final = DATA / "raw"
PROCESSED: Final = DATA / "processed"
MANIFEST_JSON: Final = DATA / "manifest.json"

NEWS_CSV: Final = PROCESSED / "noticias.csv"
EXCLUDED_NEWS_CSV: Final = PROCESSED / "noticias_excluidas.csv"
NEWS_QUALITY_JSON: Final = PROCESSED / "calidad_noticias.json"
SOURCES_JSON: Final = PROCESSED / "fuentes.json"

#: §7 minimum fields first, then ours.
NEWS_COLUMNS: Final = (
    "id_noticia",
    "titulo",
    "url",
    "medio",
    "idioma",
    "fecha_publicacion",
    "origen_fecha_publicacion",
    "fecha_deteccion",
    "fecha_extraccion",
    "tema",
    "origen",
    "alcance_texto",
    "id_fuente",
    "seccion",
    "descripcion",
    "fecha_modificacion",
)

EXCLUDED_NEWS_COLUMNS: Final = ("id_noticia", "url", "id_fuente", "origen", "motivo", "fecha_publicacion")

INDICATORS_CSV: Final = PROCESSED / "indicadores.csv"
INDICATORS_QUALITY_JSON: Final = PROCESSED / "calidad_indicadores.json"

INDICATORS_COLUMNS: Final = (
    "pais_iso3",
    "indicador_id",
    "anio",
    "valor",
    "unidad",
    "fuente_url",
    "fecha_extraccion",
    "licencia",
)

#: Team decision: INEC series from this year onward (the CPI series only starts at its 2024 base).
INEC_FROM_YEAR: Final = 2022

INEC_CSV: Final = PROCESSED / "indicadores_inec.csv"
INEC_QUALITY_JSON: Final = PROCESSED / "calidad_inec.json"

INEC_COLUMNS: Final = (
    "serie_id",
    "serie",
    "periodo",
    "frecuencia",
    "valor",
    "unidad",
    "base",
    "fuente_url",
    "fecha_extraccion",
    "licencia",
)

#: USGS supports seismic facts only, never evidence of floods or economic losses (§6.C).
EVENTS_GEOJSON: Final = PROCESSED / "eventos.geojson"
EVENTS_QUALITY_JSON: Final = PROCESSED / "calidad_eventos.json"

EVENTS_PROPERTIES: Final = (
    "id",
    "magnitude",
    "time",
    "updated",
    "longitude",
    "latitude",
    "depth",
    "place",
    "status",
    "url",
)


class PublicationDateOrigin(StrEnum):
    """Where `fecha_publicacion` came from, most reliable first (docs/research/tvn-fecha-publicacion.md)."""

    FEED = "feed"
    PAGE = "pagina"
    LASTMOD = "lastmod"

#: §3: whether the output must say it is based only on headline and metadata.
TEXT_SCOPE_HEADLINE: Final = "titular_metadatos"
TEXT_SCOPE_DESCRIPTION: Final = "titular_descripcion"
