"""R, I, U, N, E of the attention score with written rules (T08).

Every function is pure and returns `(value in 0-1, justification in Spanish)`; the justification is what the
interface shows to explain the number. Constants sit at the top, each with the reason for its value.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from whoami.contracts import EvidenceState
from whoami.pipeline.text import fold, rows_text
from whoami.schemas import Components, Member, Score

#: `id_fuente` of the official bodies in `fuentes.json`; what they publish is a primary source.
OFFICIAL_SOURCES = frozenset({"pancanal", "sinaproc", "mef", "mici", "atp", "amp"})

# R: a group is relevant when it has an editorial topic and concerns Panama; the topic weighs more because
# a Panamanian story without a topic is still not one of the six lines the newsroom covers.
TOPIC_WEIGHT = 0.6
PANAMA_WEIGHT = 0.4
PANAMA_UNKNOWN = 0.5  # neither confirmed nor ruled out
PANAMA_SECTIONS = frozenset({"nacionales", "economia"})
WORLD_SECTION = "mundo"

# I: a topic's base weight says how often it moves many people; context and scale add to it, capped at 1.
IMPACT_BASE = {
    "logistica_canal": 0.6,  # the Canal moves national revenue and trade
    "economia": 0.6,
    "servicios_publicos": 0.5,
    "eventos_naturales": 0.5,
    "regulacion": 0.5,
    "turismo": 0.4,
    "sin_tema": 0.1,  # nothing says it matters to the newsroom's lines
}
IMPACT_CONTEXT_BONUS = 0.2  # an official figure measures the topic
IMPACT_SCALE_BONUS = 0.2  # the text itself states a size

# U: hours since the newest ORIGINAL publication; each step is the next day of a story's useful life.
URGENCY_STEPS = (
    (timedelta(hours=24), 1.0),
    (timedelta(hours=48), 0.8),
    (timedelta(hours=72), 0.6),
    (timedelta(days=7), 0.4),
    (timedelta(days=14), 0.2),
)
URGENCY_FLOOR = 0.1  # old news keeps a trace of urgency, never zero
URGENCY_ALERT_BONUS = 0.2  # something is about to happen or is active

# N: similarity to earlier groups below 0.5 is a new story, above 0.9 the same story again.
NOVELTY_SIMILAR_FROM = 0.5
NOVELTY_SAME_AT = 0.9
NOVELTY_RECIRCULATED = 0.1  # old news is never a new event (T03)

# E: independent origins (up to three), a primary source and some text beyond the headline.
EVIDENCE_PROVENANCE_WEIGHT = 0.4
EVIDENCE_PROVENANCE_CAP = 3  # a fourth copy of the same story corroborates nothing more
EVIDENCE_PRIMARY_WEIGHT = 0.3
EVIDENCE_TEXT_WEIGHT = 0.3

_PANAMA_WORDS = re.compile(
    r"\b(?:panama|panama oeste|bocas del toro|cocle|colon|chiriqui|darien|herrera|los santos|veraguas|comarcas?|"
    r"asamblea|mulino)\b"
)
_PANAMA_CASE_SENSITIVE = re.compile(r"\b(?:Canal|ACP|AMP|CSS|Minsa|MEF|MICI|Idaan|Sinaproc|ATP)\b")

_SCALE_SIGNALS = (
    ("monto", re.compile(r"\$\s?\d|\b\d[\d.,]*\s+(?:millones|dolares|balboas)\b|b/\.")),
    ("porcentaje", re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|por ciento)")),
    ("alcance nacional", re.compile(r"(?<!asamblea )\bnacional\b|\btodo el pais\b")),
    (
        "personas o viviendas afectadas",
        re.compile(r"\b\d[\d.,]*\s+(?:personas|viviendas|casas|familias|hogares|afectad\w+|damnificad\w+)\b"),
    ),
)

_ALERT_WORDS = re.compile(r"\b(?:aviso|alerta|a partir del)\b")
_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_DATE_MENTION = re.compile(rf"\b(\d{{1,2}}) de ({'|'.join(_MONTHS)})(?: de (\d{{4}}))?\b")


def _is_official(row: Mapping[str, str]) -> bool:
    return row["id_fuente"] in OFFICIAL_SOURCES


def _mentions_panama(row: Mapping[str, str]) -> bool:
    text = rows_text([row])
    return bool(_PANAMA_WORDS.search(fold(text)) or _PANAMA_CASE_SENSITIVE.search(text))


# ------------------------------------------------------------------------------------------------ R


def relevance(topic: str, rows: Sequence[Mapping[str, str]]) -> tuple[float, str]:
    has_topic = topic != "sin_tema"
    if any(_mentions_panama(row) for row in rows):
        panama, panama_why = 1.0, "el texto menciona Panamá o una de sus instituciones"
    elif any(_is_official(row) or row["seccion"] in PANAMA_SECTIONS for row in rows):
        panama, panama_why = 1.0, "proviene de una fuente oficial panameña o de una sección nacional"
    elif all(row["seccion"] == WORLD_SECTION for row in rows):
        panama, panama_why = 0.0, "es de la sección Mundo y no menciona Panamá"
    else:
        panama, panama_why = PANAMA_UNKNOWN, "no se puede confirmar ni descartar el vínculo con Panamá"
    value = TOPIC_WEIGHT * has_topic + PANAMA_WEIGHT * panama
    topic_why = f"tiene tema ({topic})" if has_topic else "no tiene tema editorial"
    return round(value, 4), f"{topic_why.capitalize()}; {panama_why}."


# ------------------------------------------------------------------------------------------------ I


def impact(topic: str, text: str, has_context: bool) -> tuple[float, str]:
    base = IMPACT_BASE[topic]
    parts = [f"base {base:.1f} por el tema {topic}"]
    value = base
    if has_context:
        value += IMPACT_CONTEXT_BONUS
        parts.append(f"+{IMPACT_CONTEXT_BONUS} por contexto oficial")
    folded = fold(text)
    signal = next((name for name, pattern in _SCALE_SIGNALS if pattern.search(folded)), None)
    if signal:
        value += IMPACT_SCALE_BONUS
        parts.append(f"+{IMPACT_SCALE_BONUS} por señal de escala ({signal})")
    return round(min(value, 1.0), 4), "; ".join(parts).capitalize() + "."


# ------------------------------------------------------------------------------------------------ U


def _announces_future_or_alert(text: str, cutoff: datetime) -> bool:
    folded = fold(text)
    if _ALERT_WORDS.search(folded):
        return True
    for day, month, year in _DATE_MENTION.findall(folded):
        try:
            mentioned = datetime(int(year or cutoff.year), _MONTHS.index(month) + 1, int(day), tzinfo=UTC)
        except ValueError:
            continue
        if mentioned.date() > cutoff.date():
            return True
    return False


def urgency(newest_original: datetime, text: str, fecha_corte: datetime) -> tuple[float, str]:
    age = fecha_corte - newest_original
    value = next((step_value for limit, step_value in URGENCY_STEPS if age < limit), URGENCY_FLOOR)
    hours = max(age.total_seconds() // 3600, 0)
    why = f"La noticia original más reciente tiene {int(hours)} h al corte"
    if _announces_future_or_alert(text, fecha_corte):
        value += URGENCY_ALERT_BONUS
        why += f"; +{URGENCY_ALERT_BONUS} por aviso, alerta o fecha futura en el texto"
    return round(min(value, 1.0), 4), why + "."


# ------------------------------------------------------------------------------------------------ N


def novelty(max_similarity: float, recirculated: bool) -> tuple[float, str]:
    if recirculated:
        return NOVELTY_RECIRCULATED, "Todas las noticias son republicaciones: no es un hecho nuevo."
    span = NOVELTY_SAME_AT - NOVELTY_SIMILAR_FROM
    value = min(max((NOVELTY_SAME_AT - max_similarity) / span, 0.0), 1.0)
    return round(value, 4), f"Similitud máxima con grupos anteriores: {max_similarity:.2f}."


# ------------------------------------------------------------------------------------------------ E


def evidence_component(n_provenances: int, has_primary: bool, has_text: bool) -> tuple[float, str]:
    counted = min(n_provenances, EVIDENCE_PROVENANCE_CAP)
    value = EVIDENCE_PROVENANCE_WEIGHT * counted / EVIDENCE_PROVENANCE_CAP
    value += EVIDENCE_PRIMARY_WEIGHT * has_primary + EVIDENCE_TEXT_WEIGHT * has_text
    why = (
        f"{n_provenances} procedencia(s) independiente(s); "
        f"{'con' if has_primary else 'sin'} fuente primaria oficial; "
        f"{'con' if has_text else 'sin'} texto más allá del titular."
    )
    return round(value, 4), why


def evidence_state(rows: Sequence[Mapping[str, str]], n_provenances: int, has_context: bool) -> EvidenceState:
    """Independent of the score: what a draft could stand on."""
    has_text = any(row.get("descripcion") for row in rows)
    if any(_is_official(row) and row.get("descripcion") for row in rows) or (n_provenances >= 2 and has_text):
        return "suficiente_para_borrador"
    if has_text or has_context or n_provenances >= 2:
        return "parcial"
    return "insuficiente"


# ------------------------------------------------------------------------------------------------ Score


def score_group(
    rows: Sequence[Mapping[str, str]],
    members: Sequence[Member],
    topic: str,
    has_context: bool,
    max_similarity: float,
    fecha_corte: datetime,
) -> Score:
    """`rows` and `members` describe the same news items; `max_similarity` is computed from embeddings elsewhere."""
    text = rows_text(rows)
    recirculated = all(member.recirculada_en is not None for member in members)
    newest_original = max(member.fecha_publicacion for member in members)
    n_provenances = len({member.procedencia for member in members})
    has_primary = has_context or any(_is_official(row) for row in rows)
    has_text = any(row.get("descripcion") for row in rows)

    parts = {
        "R": relevance(topic, rows),
        "I": impact(topic, text, has_context),
        "U": urgency(newest_original, text, fecha_corte),
        "N": novelty(max_similarity, recirculated),
        "E": evidence_component(n_provenances, has_primary, has_text),
    }
    components = Components(**{name: value for name, (value, _) in parts.items()})
    return Score.from_components(components, {name: why for name, (_, why) in parts.items()})
