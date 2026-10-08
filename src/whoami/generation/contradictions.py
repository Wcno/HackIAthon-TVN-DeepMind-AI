"""Contradictions inside one group (T05): incompatible figures or dates for the same thing.

Two news items contradict each other only when they are two voices: distinct provenances, or the same provenance
at different dates (a correction). An agency republished by three outlets is one voice.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Protocol

from whoami.generation.jsonschemas import contradiction_pair_schema, response_format
from whoami.generation.prompting import build_messages
from whoami.generation.retrieval import tokenize
from whoami.generation.verifier import fold, parse_digits
from whoami.llm.client import LLMError
from whoami.schemas import Contradiction, ContradictionVersion, Evidence, Group, Member

MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
    "noviembre", "diciembre",
)  # fmt: skip
#: Modifiers shared by many metrics ("inflación anual", "PIB anual"): they do not identify one.
GENERIC_WORDS = frozenset({"anual", "mensual", "diario", "semanal", "total", "interanual", "promedio", "nuevo"})
CONTEXT_WORDS = 3
SHORT_ANSWER_MAX_TOKENS = 300
NOT_EVENT_VERBS = frozenset({"partir", "haber", "estar", "poder"})

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[^\W\d_]+")
_PERCENT = re.compile(r"\s*(?:%|por\s+ciento)")
_DAY_OF_MONTH = re.compile(rf"\s*de\s+(?:{'|'.join(MONTHS)})\b", re.IGNORECASE)
_DATE = re.compile(rf"(\d{{1,2}})\s+de\s+({'|'.join(MONTHS)})(?:\s+de\s+(\d{{4}}))?", re.IGNORECASE)
_SENTENCE_BREAK = re.compile(r"[;!?\n]|\.(?=\s)")
_MULTIPLIERS = frozenset({"mil", "millon", "millones"})
_VERB_ENDING = re.compile(r"(?:ará|erá|irá|ó|aron|ieron|arán|erán|irán|aría|ería|iría|ado|ido|ando|iendo)$")
_INFINITIVE = re.compile(r"(?:ar|er|ir)$")


class ContradictionChecker(Protocol):
    def check(self, group: Group, evidences: Mapping[str, Evidence]) -> tuple[Contradiction, ...]: ...


@dataclass(frozen=True)
class _Voice:
    member: Member
    text: str


def _voices(group: Group, evidences: Mapping[str, Evidence]) -> Iterator[tuple[_Voice, _Voice]]:
    """Pairs of members that count as two voices, with the text of their evidence."""
    voices = [
        _Voice(member, "\n".join(evidences[member.id_noticia].campos.values()))
        for member in group.miembros
        if member.id_noticia in evidences
    ]
    for first, second in combinations(voices, 2):
        different_provenance = first.member.procedencia != second.member.procedencia
        if different_provenance or first.member.fecha_publicacion != second.member.fecha_publicacion:
            yield first, second


def _spanish_date(member: Member) -> str:
    date = member.fecha_publicacion.date()
    return f"{date.day} de {MONTHS[date.month - 1]} de {date.year}"


def _scope(member: Member) -> str:
    return f"{member.medio}, {_spanish_date(member)}"


def _pair_version(value: str, voice: _Voice) -> ContradictionVersion:
    return ContradictionVersion(valor=value, alcance=_scope(voice.member), id_evidencia=voice.member.id_noticia)


# ---------------------------------------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Figure:
    value: Decimal
    shown: str
    keys: dict[tuple[str, str], str]  # metric key -> the word to show for it


def _content_words(text: str) -> list[tuple[str, str]]:
    """(stem, original word) for the content words of `text`."""
    pairs = []
    for word in _WORD.findall(text):
        stems = [stem for stem in tokenize(word) if not stem.isdigit()]
        if stems:
            pairs.append((stems[0], word))
    return pairs


def _figures(text: str) -> list[_Figure]:
    figures = []
    for match in _NUMBER.finditer(text):
        values = parse_digits(match.group())
        before, after = text[: match.start()], text[match.end() :]
        is_year = len(match.group()) == 4 and 1900 <= values[0] <= 2100
        glued = match.start() > 0 and (text[match.start() - 1].isalnum() or text[match.start() - 1] in ":/-")
        if len(values) != 1 or is_year or glued or _DAY_OF_MONTH.match(after) or after[:1] in (":", "/"):
            continue
        value = values[0]
        if _PERCENT.match(after):
            context = _content_words(_SENTENCE_BREAK.split(before)[-1])[-CONTEXT_WORDS:]
            keys = {("%", stem): word.casefold() for stem, word in context if stem not in GENERIC_WORDS}
            figures.append(_Figure(value, f"{match.group()} %", keys))
            continue
        following = _content_words(after[:80])
        while following and fold(following[0][1]) in _MULTIPLIERS:
            following = following[1:]
        if following:
            stem, word = following[0]
            figures.append(_Figure(value, f"{match.group()} {word}", {("unidad", stem): word.casefold()}))
    return figures


def _first_conflict(first: _Voice, second: _Voice) -> Contradiction | None:
    figures_a, figures_b = _figures(first.text), _figures(second.text)
    shared = {key for f in figures_a for key in f.keys} & {key for f in figures_b for key in f.keys}
    for key in sorted(shared):
        side_a = [f for f in figures_a if key in f.keys]
        side_b = [f for f in figures_b if key in f.keys]
        if {f.value for f in side_a}.isdisjoint(f.value for f in side_b):
            label = side_a[0].keys[key]
            return Contradiction(
                descripcion=f"Cifras distintas para «{label}»: {side_a[0].shown} y {side_b[0].shown}.",
                versiones=(_pair_version(side_a[0].shown, first), _pair_version(side_b[0].shown, second)),
            )
    return None


def numeric_conflicts(group: Group, evidences: Mapping[str, Evidence]) -> tuple[Contradiction, ...]:
    """Same metric (same unit, or same percent subject) with different values in two voices of the group."""
    conflicts = (_first_conflict(first, second) for first, second in _voices(group, evidences))
    return tuple(conflict for conflict in conflicts if conflict)


# ---------------------------------------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _EventDate:
    shown: str
    key: tuple[int, str, str | None]
    verb: str  # folded stem identifying the event
    verb_word: str


def _is_verb(word: str) -> bool:
    folded = fold(word)
    if folded in NOT_EVENT_VERBS:
        return False
    lowered = word.casefold()
    return bool(_VERB_ENDING.search(lowered) or (len(lowered) >= 6 and _INFINITIVE.search(lowered)))


def _event_dates(text: str) -> list[_EventDate]:
    events = []
    for sentence in _SENTENCE_BREAK.split(text):
        for match in _DATE.finditer(sentence):
            before = [w for w in _WORD.findall(sentence[: match.start()]) if _is_verb(w)]
            after = [w for w in _WORD.findall(sentence[match.end() :]) if _is_verb(w)]
            verb = (before[-1:] or after[:1] or [None])[0]
            if verb is None:
                continue
            day, month, year = match.groups()
            key = (int(day), month.casefold(), year)
            shown = f"{day} de {month.casefold()}" + (f" de {year}" if year else "")
            events.append(_EventDate(shown, key, fold(verb)[:5], verb.casefold()))
    return events


def _same_date(a: tuple[int, str, str | None], b: tuple[int, str, str | None]) -> bool:
    return a[:2] == b[:2] and (a[2] is None or b[2] is None or a[2] == b[2])


def _first_date_conflict(first: _Voice, second: _Voice) -> Contradiction | None:
    dates_a, dates_b = _event_dates(first.text), _event_dates(second.text)
    for verb in dict.fromkeys(e.verb for e in dates_a):
        side_a = [e for e in dates_a if e.verb == verb]
        side_b = [e for e in dates_b if e.verb == verb]
        if side_b and not any(_same_date(a.key, b.key) for a in side_a for b in side_b):
            return Contradiction(
                descripcion=f"Fechas distintas para «{side_a[0].verb_word}»: {side_a[0].shown} y {side_b[0].shown}.",
                versiones=(_pair_version(side_a[0].shown, first), _pair_version(side_b[0].shown, second)),
            )
    return None


def date_conflicts(group: Group, evidences: Mapping[str, Evidence]) -> tuple[Contradiction, ...]:
    """Different explicit dates for the same event verb in two voices of the group."""
    conflicts = (_first_date_conflict(first, second) for first, second in _voices(group, evidences))
    return tuple(conflict for conflict in conflicts if conflict)


# ---------------------------------------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------------------------------------


class RuleBasedChecker:
    def check(self, group: Group, evidences: Mapping[str, Evidence]) -> tuple[Contradiction, ...]:
        return numeric_conflicts(group, evidences) + date_conflicts(group, evidences)


class LLMContradictionChecker:
    """Asks the model about each pair of voices. Unusable answers are ignored."""

    TASK = (
        "Compara las dos fuentes. contradiccion es true solo si afirman cosas incompatibles sobre lo mismo "
        "(cifras o fechas distintas). Si es true, describe la diferencia y da valor_a (primera fuente) y "
        "valor_b (segunda fuente) tal como aparecen."
    )

    def __init__(self, llm, model: str) -> None:
        self._llm = llm
        self._model = model

    def check(self, group: Group, evidences: Mapping[str, Evidence]) -> tuple[Contradiction, ...]:
        found = (self._check_pair(first, second, evidences) for first, second in _voices(group, evidences))
        return tuple(contradiction for contradiction in found if contradiction)

    def _check_pair(self, first: _Voice, second: _Voice, evidences: Mapping[str, Evidence]) -> Contradiction | None:
        pair: Sequence[Evidence] = [evidences[first.member.id_noticia], evidences[second.member.id_noticia]]
        try:
            completion = self._llm.complete(
                self._model,
                build_messages(self.TASK, pair),
                purpose="contradiccion",
                evidence_ids=[e.id_evidencia for e in pair],
                response_format=response_format("contradiccion", contradiction_pair_schema()),
                max_tokens=SHORT_ANSWER_MAX_TOKENS,
            )
            data = completion.json()
            if data["contradiccion"] is not True:
                return None
            return Contradiction(
                descripcion=data["descripcion"],
                versiones=(_pair_version(data["valor_a"], first), _pair_version(data["valor_b"], second)),
            )
        except (LLMError, ValueError, KeyError, TypeError, AttributeError):
            return None
