"""Official context by explicit rules (T04): an indicator or event is linked only when the news names its topic.

A group that no rule covers says so (`sin_contexto_motivo`); a link is never forced. The matcher is pluggable:
`link_context` takes the list of rules, so an embedding-based linker can be compared against these later.
"""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from whoami.pipeline.text import fold, word_pattern
from whoami.schemas import ContextLink, Evidence

#: A quake explains a news item only when it happened within a day of the earliest report.
QUAKE_WINDOW = timedelta(days=1)
#: Headlines round or approximate magnitudes, and USGS revises them.
MAGNITUDE_TOLERANCE = 0.3

COUNTRY = "PAN"
NO_CONTEXT_REASON = "Ningún indicador ni evento oficial del paquete mide este tema; no se fuerza un vínculo."
NO_QUAKE_REASON = "Ningún sismo del catálogo USGS coincide en fecha con la noticia."

#: Finds the official record a rule points at: (official evidence, group text as written, earliest member date).
EvidenceFinder = Callable[[Mapping[str, Evidence], str, datetime], Evidence | None]


@dataclass(frozen=True)
class ContextRule:
    """Fires when a keyword appears as a whole word (accent and case insensitive).

    `topics` narrows ambiguous keywords: when it is empty the rule fires for any topic.
    `sin_evidencia_motivo` is what the group says when the rule fires but `evidence` finds nothing.
    """

    name: str
    keywords: tuple[str, ...]
    topics: frozenset[str]
    evidence: EvidenceFinder
    razon: str
    sin_evidencia_motivo: str = NO_CONTEXT_REASON

    def matched_keyword(self, folded_text: str, topic: str) -> str | None:
        if self.topics and topic not in self.topics:
            return None
        match = word_pattern(tuple(fold(keyword) for keyword in self.keywords)).search(folded_text)
        return match.group(0) if match else None


def latest_point(prefix: str) -> EvidenceFinder:
    """The most recent period with a value among the evidence ids that start with `prefix`."""

    def find(official: Mapping[str, Evidence], text: str, earliest: datetime) -> Evidence | None:
        points = [e for key, e in official.items() if key.startswith(prefix) and e.campos["valor"] != ""]
        return max(points, key=lambda e: e.campos["periodo"], default=None)

    return find


def first_found(*finders: EvidenceFinder) -> EvidenceFinder:
    def find(official: Mapping[str, Evidence], text: str, earliest: datetime) -> Evidence | None:
        return next((found for finder in finders if (found := finder(official, text, earliest))), None)

    return find


_MAGNITUDE = r"(\d+(?:[.,]\d+)?)"
_MAGNITUDE_PATTERNS = (
    re.compile(rf"magnitud\s+(?:de\s+)?{_MAGNITUDE}"),
    re.compile(rf"{_MAGNITUDE}\s*(?:grados|de magnitud|en la escala)"),
)
_LETTER_M = re.compile(rf"\bM\s?{_MAGNITUDE}")


def magnitudes_in(text: str) -> list[float]:
    folded = fold(text)
    found = [m for pattern in _MAGNITUDE_PATTERNS for m in pattern.findall(folded)]
    found += _LETTER_M.findall(text)
    return [float(value.replace(",", ".")) for value in found]


def _matches_stated_magnitude(evidence: Evidence, stated: list[float]) -> bool:
    magnitude = float(evidence.campos["valor"].replace(",", "."))
    return not stated or any(round(abs(magnitude - value), 1) <= MAGNITUDE_TOLERANCE for value in stated)


#: Latitude and longitude range of Panama; an epicenter inside it counts as a Panamanian quake.
PANAMA_LATITUDES = (7.0, 9.7)
PANAMA_LONGITUDES = (-83.1, -77.1)

#: Countries a quake story can be about instead of Panama; the folded names are matched as whole words.
#: Estados Unidos is left out on purpose: "Servicio Geológico de Estados Unidos" appears in Panamanian quake news.
_OTHER_COUNTRIES = word_pattern(
    tuple(
        fold(name)
        for name in (
            "Colombia", "Costa Rica", "México", "Chile", "Perú", "Ecuador", "Guatemala", "Japón", "Nicaragua",
            "Honduras", "El Salvador", "Venezuela", "Argentina", "Bolivia", "Haití", "Cuba", "Turquía",
            "Indonesia", "Filipinas", "China", "Irán", "Italia", "Grecia", "Nepal", "Nueva Zelanda",
        )
    )
)
_PANAMANIAN_REGIONS = word_pattern(
    tuple(
        fold(name)
        for name in (
            "Bocas del Toro", "Chiriquí", "Veraguas", "Coclé", "Herrera", "Los Santos", "Colón", "Panamá Oeste",
            "Darién", "Guna Yala", "Emberá-Wounaan", "Ngäbe-Buglé",
        )
    )
)


def _is_in_panama(quake: Evidence) -> bool:
    """The USGS place names Panama, or the epicenter (when the catalog gives it) is inside Panama's box."""
    if "panama" in fold(quake.campos["lugar"]):
        return True
    try:
        latitude, longitude = float(quake.campos["latitud"]), float(quake.campos["longitud"])
    except (KeyError, ValueError):
        return False
    return PANAMA_LATITUDES[0] <= latitude <= PANAMA_LATITUDES[1] and PANAMA_LONGITUDES[0] <= longitude <= PANAMA_LONGITUDES[1]


def _names_another_country(text: str) -> bool:
    """The news places the event in another country and never in a Panamanian province."""
    folded = fold(text)
    return bool(_OTHER_COUNTRIES.search(folded)) and not _PANAMANIAN_REGIONS.search(folded)


def closest_quake(official: Mapping[str, Evidence], text: str, earliest: datetime) -> Evidence | None:
    """The USGS event nearest in time within a day, in Panama; a magnitude written in the text must match.

    A news item about a quake in another country is never linked, even when the catalog box holds an event."""
    if _names_another_country(text):
        return None
    stated = magnitudes_in(text)
    candidates = [
        (abs(e.fecha - earliest), e)
        for key, e in official.items()
        if key.startswith("USGS-")
        and e.fecha is not None
        and abs(e.fecha - earliest) <= QUAKE_WINDOW
        and _is_in_panama(e)
        and _matches_stated_magnitude(e, stated)
    ]
    return min(candidates, key=lambda pair: pair[0], default=(None, None))[1]


_MACRO_TOPICS = frozenset({"economia", "logistica_canal", "turismo"})

DEFAULT_RULES: tuple[ContextRule, ...] = (
    ContextRule(
        name="inflacion",
        keywords=("inflación", "IPC", "precios al consumidor", "costo de la vida"),
        topics=frozenset(),
        evidence=latest_point("INEC-ipc_var_interanual-"),
        razon="El grupo habla de inflación o precios; el IPC interanual del INEC mide ese tema.",
    ),
    ContextRule(
        name="desempleo",
        keywords=("desempleo", "tasa de desempleo"),
        topics=frozenset(),
        evidence=latest_point("WB-PAN-SL.UEM.TOTL.ZS-"),
        razon="El grupo habla de desempleo; la tasa de desempleo del Banco Mundial mide ese tema.",
    ),
    ContextRule(
        name="pib",
        keywords=("PIB", "crecimiento económico", "economía creció", "economía crece"),
        topics=_MACRO_TOPICS,
        evidence=first_found(
            latest_point("INEC-pib_constante_var_interanual-"), latest_point("WB-PAN-NY.GDP.MKTP.KD.ZG-")
        ),
        razon="El grupo habla del crecimiento de la economía; la variación del PIB mide ese tema.",
    ),
    ContextRule(
        name="exportaciones",
        keywords=("exportaciones", "exportación"),
        topics=_MACRO_TOPICS,
        evidence=latest_point("WB-PAN-NE.EXP.GNFS.ZS-"),
        razon="El grupo habla de exportaciones; el peso de las exportaciones en el PIB mide ese tema.",
    ),
    ContextRule(
        name="sismo",
        keywords=("sismo", "sismos", "temblor", "temblores", "terremoto", "terremotos"),
        topics=frozenset(),
        evidence=closest_quake,
        razon="El grupo habla de un sismo; el catálogo USGS registra un evento en esa fecha.",
        sin_evidencia_motivo=NO_QUAKE_REASON,
    ),
)


def _label(evidence: Evidence) -> str:
    match evidence.tipo:
        case "indicador":
            return evidence.campos["indicador"]
        case "serie_inec":
            return evidence.campos["serie"]
        case _:
            return f"Sismo M{evidence.campos['valor']}"


def _limitations(evidence: Evidence) -> str:
    fields = evidence.campos
    match evidence.tipo:
        case "indicador":
            return f"Serie anual del Banco Mundial ({fields['periodo']}): describe ese año, no la situación de hoy."
        case "serie_inec":
            return f"Dato {fields['frecuencia']} del INEC ({fields['periodo']}, base {fields['base']}); puede revisarse."
        case _:
            return "El catálogo USGS confirma el sismo (hora, magnitud, lugar); no mide daños, pérdidas ni afectados."


def link_context(
    group_text: str,
    earliest_date: datetime,
    topic: str,
    official: Mapping[str, Evidence],
    rules: Iterable[ContextRule] = DEFAULT_RULES,
) -> tuple[tuple[ContextLink, ...], str | None]:
    """Links per rule that fires, and the reason there is none when nothing could be linked."""
    folded = fold(group_text)
    links: dict[str, ContextLink] = {}
    unfound_reasons: list[str] = []
    for rule in rules:
        keyword = rule.matched_keyword(folded, topic)
        if keyword is None:
            continue
        evidence = rule.evidence(official, group_text, earliest_date)
        if evidence is None:
            unfound_reasons.append(rule.sin_evidencia_motivo)
            continue
        links.setdefault(
            evidence.id_evidencia,
            ContextLink(
                id_evidencia=evidence.id_evidencia,
                etiqueta=_label(evidence),
                pais=COUNTRY,
                limitaciones=_limitations(evidence),
                razon=f"{rule.razon} Coincide con «{keyword}».",
            ),
        )
    reason = None if links else next(iter(unfound_reasons), NO_CONTEXT_REASON)
    return tuple(links.values()), reason
