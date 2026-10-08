"""View helpers for the master/detail shell: snapshot line, dates and draft budgets."""

from datetime import datetime
from pathlib import Path

from whoami.backend.panama_time import panama_time
from whoami.backend.reports import quality_view
from whoami.contracts import BRIEF_MAX_WORDS, COPY_MAX_WORDS, SCRIPT_SECONDS, SPOKEN_WORDS_PER_SECOND

BUDGETS = {"brief": (BRIEF_MAX_WORDS, None, "palabras"), "guion": (SCRIPT_SECONDS[1], SCRIPT_SECONDS[0], "s"),
           "copy": (COPY_MAX_WORDS, None, "palabras")}


def snapshot_view(directory: Path) -> dict:
    """Counts and cutoff shown on every desk page; read once at startup from the same data as /quality."""
    view = quality_view(directory)
    tally = (view["news"] or {}).get("tally")
    return {"tally": tally, "cutoff": (view["snapshot"] or {}).get("cutoff")}


def latest_date(group: dict) -> str | None:
    dates = [member.get("recirculada_en") or member["fecha_publicacion"] for member in group["miembros"]]
    return max(dates, key=lambda value: datetime.fromisoformat(value)) if dates else None


def needs_investigation(group: dict) -> bool:
    return group["puntaje"]["rango"] == "alto" and group["estado_evidencia"] == "insuficiente"


def word_count(text: str | None) -> int:
    return len((text or "").split())


def spoken_seconds(text: str | None) -> int:
    return round(word_count(text) / SPOKEN_WORDS_PER_SECOND)


def budget(value: int, maximum: int, unit: str, minimum: int | None = None) -> dict:
    state = "is-over" if value > maximum else "is-under" if minimum and value < minimum else ""
    return {"amount": value, "maximum": maximum, "unit": unit, "state": state, "percent": min(100, round(value / maximum * 100)),
            "range": f"{minimum}-{maximum}" if minimum else str(maximum)}


def draft_budgets(draft: dict) -> dict:
    brief, script, copy = (BUDGETS[key] for key in ("brief", "guion", "copy"))
    return {"brief": budget(word_count(draft["brief"]), brief[0], brief[2]),
            "guion": budget(spoken_seconds(draft["guion"]), script[0], script[2], script[1]),
            "copy": budget(word_count(draft["copy_digital"]), copy[0], copy[2])}


EVIDENCE_KINDS = {"noticia": "Noticia", "indicador": "Indicador oficial", "serie_inec": "Indicador oficial (INEC)", "sismo": "Sismo (USGS)"}
FIELD_LABELS = {
    "titulo": "Título", "medio": "Medio", "fecha_publicacion": "Fecha de publicación", "descripcion": "Descripción",
    "indicador": "Indicador", "periodo": "Período", "valor": "Valor", "unidad": "Unidad", "serie": "Serie", "base": "Base",
    "frecuencia": "Frecuencia", "lugar": "Lugar", "hora_utc": "Hora (UTC)", "estado": "Estado", "latitud": "Latitud", "longitud": "Longitud",
}
#: Shown once in the source header instead of again among the passages.
HEADER_FIELDS = ("titulo", "fecha_publicacion")


def pluralize(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key.replace("_", " ").capitalize())


def evidence_card(evidence: dict) -> dict:
    """A source as the editor reads it: kind, headline, one formatted date and labelled passages."""
    return {"tipo": EVIDENCE_KINDS.get(evidence["tipo"], "Fuente"), "titulo": evidence["titulo"],
            "fecha": panama_time(evidence["fecha"]) if evidence["fecha"] else None, "url": evidence["url"],
            "campos": [{"etiqueta": field_label(key), "valor": value} for key, value in evidence["campos"].items() if key not in HEADER_FIELDS]}


def source_line(evidence: dict) -> dict:
    """Headline and outlet (or kind of source) that identify a citation in a list of sources."""
    return {"titulo": evidence["titulo"], "detalle": evidence["campos"].get("medio") or EVIDENCE_KINDS.get(evidence["tipo"], "Fuente")}
