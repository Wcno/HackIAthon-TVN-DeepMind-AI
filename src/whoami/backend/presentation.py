"""View helpers for the master/detail shell: snapshot line, dates and draft budgets."""

from datetime import datetime
from pathlib import Path

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


GENERIC_NEXT_STEP = "Agrega una fuente que trate este tema directamente o prueba con una pregunta más concreta."
#: What the query box writes when it has nothing specific to ask for; it only repeats the question.
GENERIC_MISSING_PREFIX = "Fuentes que respondan directamente"


def sentence(text: str) -> str:
    text = text.strip()
    return text if not text else text[0].upper() + text[1:] + ("" if text[-1] in ".!?" else ".")


def abstention_copy(answer: dict) -> dict:
    """The reason and next step of an abstention as readable sentences; a next step that only repeats the question
    becomes a real one."""
    missing = (answer.get("faltante") or "").strip()
    generic = not missing or missing.startswith(GENERIC_MISSING_PREFIX)
    return {"reason": sentence(answer.get("motivo_abstencion") or "Las fuentes no responden la consulta"),
            "next_step": GENERIC_NEXT_STEP if generic else sentence(missing)}
