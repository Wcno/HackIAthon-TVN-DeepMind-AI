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

#: Pipeline outputs (G3, G4) and the synthetic set the frontend starts from (G2). Same file names in
#: both places, so the interface switches between them by changing a directory.
OUTPUTS: Final = DATA.parent / "outputs"
DEMO: Final = DATA / "demo"
GROUPS_FILE: Final = "grupos.jsonl"  # processed/: groups with members, score and official context
EVIDENCE_FILE: Final = "evidencias.jsonl"  # processed/: every citable record
FICHAS_FILE: Final = "fichas.jsonl"  # outputs/: §7
QUERIES_FILE: Final = "consultas.jsonl"  # outputs/: precomputed answers (offline, D-01)
REVIEWS_FILE: Final = "revisiones.jsonl"  # outputs/: human decisions, append-only history

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
TEXT_SCOPE_FULL: Final = "texto_completo"
TEXT_SCOPES: Final = (TEXT_SCOPE_HEADLINE, TEXT_SCOPE_DESCRIPTION, TEXT_SCOPE_FULL)

#: §3: a draft built only on headline and metadata must carry this wording.
HEADLINE_ONLY_LEGEND: Final = "basado únicamente en titular/metadatos"

#: §4 attention score: P = 30R + 25I + 20U + 15N + 10E, each component normalised to 0-1.
SCORE_WEIGHTS: Final = {"R": 30, "I": 25, "U": 20, "N": 15, "E": 10}

#: §4 ranges, no overlap: bajo [0,40), medio [40,70), alto [70,100].
SCORE_RANGES: Final = (("bajo", 0, 40), ("medio", 40, 70), ("alto", 70, 100))

#: Bump when weights or component rules change, so a score can be traced to its rules (§4).
RULES_VERSION: Final = "1.0.0"

#: Evidence id prefixes, one per kind of source. Ids are stable so a citation can be checked later.
#: noticia: `N-<hash>` (noticias.csv), indicador: `WB-PAN-NY.GDP.MKTP.KD.ZG-2023`,
#: serie_inec: `INEC-ipc_indice-2024-01`, sismo: `USGS-us6000rerc`.
EVIDENCE_PREFIXES: Final = {"noticia": "N-", "indicador": "WB-", "serie_inec": "INEC-", "sismo": "USGS-"}

#: §3 stage 6: the draft must tell these four apart.
CLAIM_TYPES: Final = ("hecho", "declaracion", "inferencia", "hipotesis")

#: §3 stage 2 topics as stable slugs. `sin_tema` is ours: no description passed the threshold, so
#: the topic is not forced. TOPIC_LABELS are the names the interface shows.
TOPICS: Final = ("economia", "logistica_canal", "turismo", "servicios_publicos", "eventos_naturales", "regulacion")
NO_TOPIC: Final = "sin_tema"
TOPIC_LABELS: Final = {
    "economia": "Economía",
    "logistica_canal": "Logística/Canal",
    "turismo": "Turismo",
    "servicios_publicos": "Servicios públicos",
    "eventos_naturales": "Eventos naturales",
    "regulacion": "Regulación",
    "sin_tema": "Sin tema",
}

#: §8 human review states. Approving a draft does not mean publishing it.
REVIEW_STATES: Final = ("nuevo", "en_revision", "requiere_evidencia", "aprobado_como_borrador", "descartado")

#: §4 evidence status, independent of the score.
EVIDENCE_STATES: Final = ("insuficiente", "parcial", "suficiente_para_borrador")

MODALITY: Final = "editorial_tvn"

#: §3 editorial package limits.
BRIEF_MAX_WORDS: Final = 250
COPY_MAX_WORDS: Final = 80
RESEARCH_QUESTIONS: Final = 3

#: Outcome of a query box answer: answered with citations, abstained, or showing both versions.
ANSWER_STATES: Final = ("respondida", "abstencion", "contradiccion")
