"""Deterministic citation check plus Spanish number handling.

The model proposes claims; this module decides which survive. A claim survives when every citation is literal
(after a conservative repair), every figure it states appears in what it cites, official figures carry their
period and are not called current, and an accusation is not stated as fact.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from math import ceil, floor

from whoami.generation.untrusted import restore_brackets
from whoami.schemas import CaseFile, Citation, Claim, Evidence, citation_errors

OFFICIAL_KINDS = ("indicador", "serie_inec")
REPAIR_MIN_RATIO = 0.9
REPAIR_WINDOW_TOLERANCE = 0.2
MIN_ANCHOR_BLOCK = 3

_PRESENT_FRAMING = re.compile(r"\b(actual|actualmente|hoy|en este momento|vigente)\b")
_ACCUSATIONS = re.compile(r"\b(robó|malversó|estafó|es culpable|cometió|corrupto)\b")


def fold(text: str) -> str:
    """Lowercase without accents: the form in which texts are compared."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


# ---------------------------------------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------------------------------------

_UNITS = {
    "cero": 0, "uno": 1, "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiun": 21, "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}  # fmt: skip
_TENS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}  # fmt: skip
_HUNDREDS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500, "seiscientos": 600,
    "seiscientas": 600, "setecientos": 700, "setecientas": 700, "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}  # fmt: skip
_BELOW_THOUSAND = _UNITS | _TENS | _HUNDREDS
_MILLION = ("millon", "millones")
_ARTICLES = ("un", "uno", "una")
_CONNECTABLE_UNITS = {word for word, value in _UNITS.items() if 1 <= value <= 9}

_TOKEN = re.compile(r"(?<!\w)[+−-]?\d+(?:[.,]\d+)*|\d+(?:[.,]\d+)*|[a-z]+")


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int

    @property
    def is_number(self) -> bool:
        return self.text.lstrip("+−-")[0].isdigit()


def parse_digits(token: str) -> list[Decimal]:
    """`1.500` and `1,500` are 1500; `1,5` and `1.5` are 1.5; `1.234,56` and `1,234.56` are 1234.56."""
    sign = -1 if token.startswith(("-", "−")) else 1
    token = token.lstrip("+−-")
    separators = re.findall(r"[.,]", token)
    if not separators:
        return [Decimal(token) * sign]
    if len(set(separators)) == 2:
        decimal_separator = token[max(token.rfind("."), token.rfind(","))]
        thousands_separator = "." if decimal_separator == "," else ","
        return [Decimal(token.replace(thousands_separator, "").replace(decimal_separator, ".")) * sign]
    parts = token.split(separators[0])
    whole, rest = parts[0], parts[1:]
    is_grouped = 1 <= len(whole) <= 3 and whole != "0" and all(len(part) == 3 for part in rest)
    if is_grouped:
        return [Decimal("".join(parts)) * sign]
    if len(parts) == 2:
        return [Decimal(f"{whole}.{rest[0]}") * sign]
    return [Decimal(part) * sign for part in parts]


def _evaluate_words(words: Sequence[str]) -> Decimal:
    total = current = 0
    for word in words:
        if word == "mil":
            total += max(current, 1) * 1000
            current = 0
        elif word in _MILLION:
            total = (total + current or 1) * 1_000_000
            current = 0
        elif word in _BELOW_THOUSAND:
            current += _BELOW_THOUSAND[word]
    return Decimal(total + current)


def _is_number_word(word: str) -> bool:
    return word in _BELOW_THOUSAND or word == "mil" or word in _MILLION


def normalize_numbers(text: str) -> list[Decimal]:
    """Every number in `text`, written in digits or Spanish words, as a `Decimal`, in order of appearance.

    Percent signs and currency symbols do not change the value; years are numbers too.
    """
    folded = fold(text)
    tokens = [_Token(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(folded)]

    def adjacent(left: int, right: int) -> bool:
        return right < len(tokens) and not folded[tokens[left].end : tokens[right].start].strip()

    numbers: list[Decimal] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        spoken_sign = -1 if index and tokens[index - 1].text == "menos" and adjacent(index - 1, index) else 1
        if token.is_number:
            values = parse_digits(token.text)
            index += 1
            if len(values) == 1:
                multiplier, index = _digit_multiplier(tokens, index, adjacent)
                values = [values[0] * multiplier]
            numbers += [value * spoken_sign for value in values]
        elif token.text == "ciento" and index and tokens[index - 1].text == "por":
            index += 1  # "por ciento" is a percent sign, not a hundred
        elif _is_number_word(token.text):
            words, index = _word_run(tokens, index, adjacent)
            if words not in (["un"], ["uno"], ["una"]):
                numbers.append(_evaluate_words(words) * spoken_sign)
        else:
            index += 1
    return numbers


def _digit_multiplier(tokens: list[_Token], index: int, adjacent) -> tuple[int, int]:
    """`32 millones`, `32 mil`, `32 mil millones`: the multiplier written after digits."""
    if not adjacent(index - 1, index) or tokens[index].is_number:
        return 1, index
    word = tokens[index].text
    if word in _MILLION:
        return 1_000_000, index + 1
    if word == "mil":
        if adjacent(index, index + 1) and tokens[index + 1].text in _MILLION:
            return 1_000_000_000, index + 2
        return 1000, index + 1
    return 1, index


def _word_run(tokens: list[_Token], index: int, adjacent) -> tuple[list[str], int]:
    """Consecutive number words, with `y` between tens and units (`treinta y tres`)."""
    words = [tokens[index].text]
    index += 1
    while adjacent(index - 1, index):
        word = tokens[index].text
        if _is_number_word(word):
            words.append(word)
            index += 1
        elif (
            word == "y"
            and words[-1] in _TENS
            and adjacent(index, index + 1)
            and tokens[index + 1].text in _CONNECTABLE_UNITS
        ):
            index += 1
        else:
            break
    return words, index


# ---------------------------------------------------------------------------------------------------------
# Passage repair
# ---------------------------------------------------------------------------------------------------------


def _fold_with_origin(text: str) -> tuple[str, list[int]]:
    """`fold(text)` plus, for each folded character, the index of the character it came from."""
    folded: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        for piece in unicodedata.normalize("NFD", char.casefold()):
            if not unicodedata.combining(piece):
                folded.append(piece)
                origin.append(index)
    return "".join(folded), origin


def repair_passage(passage: str, field_text: str) -> str | None:
    """The literal text of `field_text` the passage meant to quote, or None if there is no safe match.

    Case, accent and bracket differences alone always repair. Otherwise the closest window of the field
    (passage length plus or minus 20 %) is taken when its similarity is at least 0.9.
    """
    if passage in field_text:
        return passage
    restored = restore_brackets(passage)
    if restored in field_text:
        return restored
    folded_passage, _ = _fold_with_origin(restored)
    folded_field, origin = _fold_with_origin(field_text)
    if not folded_passage.strip():
        return None
    found = folded_field.find(folded_passage)
    if found >= 0:
        span = (found, found + len(folded_passage))
    else:
        span = _closest_window(folded_passage, folded_field)
        if span is None:
            return None
    return field_text[origin[span[0]] : origin[span[1] - 1] + 1]


def _closest_window(passage: str, field: str) -> tuple[int, int] | None:
    length = len(passage)
    slack = ceil(length * REPAIR_WINDOW_TOLERANCE)
    lengths = range(max(1, floor(length * (1 - REPAIR_WINDOW_TOLERANCE))), ceil(length * (1 + REPAIR_WINDOW_TOLERANCE)) + 1)
    blocks = SequenceMatcher(None, field, passage, autojunk=False).get_matching_blocks()
    starts = {
        start
        for block in blocks
        if block.size >= MIN_ANCHOR_BLOCK
        for start in range(block.a - block.b - slack, block.a - block.b + slack + 1)
        if 0 <= start < len(field)
    }
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(passage)
    best_ratio = REPAIR_MIN_RATIO
    best: tuple[int, int] | None = None
    for start in sorted(starts):
        for size in lengths:
            if start + size > len(field):
                break
            matcher.set_seq1(field[start : start + size])
            if matcher.real_quick_ratio() < best_ratio or matcher.quick_ratio() < best_ratio:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio or (best is None and ratio >= best_ratio):
                best_ratio, best = ratio, (start, start + size)
    if best is None:
        return None
    window = field[best[0] : best[1]]
    lead = len(window) - len(window.lstrip())
    return best[0] + lead, best[1] - (len(window) - len(window.rstrip()))


# ---------------------------------------------------------------------------------------------------------
# Citations and claims
# ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairedCitation:
    original: Citation
    repaired: Citation
    id_afirmacion: str | None = None


@dataclass(frozen=True)
class CitationCheck:
    valid: tuple[Citation, ...]
    repaired: tuple[RepairedCitation, ...]
    errors: tuple[str, ...]


def check_citations(citations: Iterable[Citation], evidences: Mapping[str, Evidence]) -> CitationCheck:
    """Repairs what can be repaired safely and separates the citations that are literal from those that are not."""
    valid: list[Citation] = []
    repaired: list[RepairedCitation] = []
    errors: list[str] = []
    for citation in citations:
        evidence = evidences.get(citation.id_evidencia)
        candidate = citation
        if evidence is not None and citation.campo in evidence.campos:
            fixed = repair_passage(citation.pasaje, evidence.campos[citation.campo])
            if fixed is not None and fixed != citation.pasaje:
                candidate = citation.model_copy(update={"pasaje": fixed})
        problems = citation_errors([candidate], evidences)
        if problems:
            errors += problems if candidate is citation else citation_errors([citation], evidences)
            continue
        valid.append(candidate)
        if candidate is not citation:
            repaired.append(RepairedCitation(original=citation, repaired=candidate))
    return CitationCheck(tuple(valid), tuple(repaired), tuple(errors))


def supported_numbers(citations: Iterable[Citation], evidences: Mapping[str, Evidence]) -> set[Decimal]:
    """Numbers of the cited passages and of every field of the cited evidence records.

    A figure taken from another field of the same record (its publication date, its period) is still grounded in
    that record; a figure from a record nobody cited is not.
    """
    supported: set[Decimal] = set()
    for citation in citations:
        evidence = evidences.get(citation.id_evidencia)
        supported.update(normalize_numbers(citation.pasaje))
        if evidence is None:
            continue
        for value in evidence.campos.values():
            supported.update(normalize_numbers(value))
    return supported


def unsupported_numbers(text: str, citations: Iterable[Citation], evidences: Mapping[str, Evidence]) -> list[Decimal]:
    supported = supported_numbers(citations, evidences)
    return [number for number in dict.fromkeys(normalize_numbers(text)) if number not in supported]


def _official_period_errors(claim: Claim, evidences: Mapping[str, Evidence]) -> list[str]:
    official = [
        evidences[c.id_evidencia]
        for c in claim.citas
        if c.id_evidencia in evidences and evidences[c.id_evidencia].tipo in OFFICIAL_KINDS
    ]
    if not official:
        return []
    errors = []
    for evidence in official:
        period = evidence.campos.get("periodo", "").strip()
        year = re.search(r"\d{4}", period)
        if not period or (period not in claim.texto and not (year and year.group() in claim.texto)):
            errors.append("cifra oficial sin período")
            break
    if _PRESENT_FRAMING.search(fold(claim.texto)):
        errors.append("cifra oficial presentada como actual")
    return errors


@dataclass(frozen=True)
class ClaimCheck:
    claim: Claim  # with repaired citations
    issues: tuple[str, ...]
    repairs: tuple[RepairedCitation, ...]


def check_claim(claim: Claim, evidences: Mapping[str, Evidence]) -> ClaimCheck:
    from whoami.generation.prompting import leaks_canary
    citations = check_citations(claim.citas, evidences)
    repairs = tuple(
        RepairedCitation(r.original, r.repaired, id_afirmacion=claim.id_afirmacion) for r in citations.repaired
    )
    issues = list(citations.errors)
    if leaks_canary(claim.model_dump_json()):
        issues.append("internal canary in generated claim")
    repaired_claim = claim.model_copy(update={"citas": citations.valid}) if not issues else claim
    issues += [
        f"cifra no respaldada: {format(number.normalize(), 'f')}"
        for number in unsupported_numbers(claim.texto, citations.valid, evidences)
    ]
    issues += _official_period_errors(repaired_claim, evidences)
    if claim.tipo == "hecho" and _ACCUSATIONS.search(claim.texto.casefold()):
        issues.append("acusación presentada como hecho")
    return ClaimCheck(repaired_claim, tuple(issues), repairs)


def verify_claim(claim: Claim, evidences: Mapping[str, Evidence]) -> list[str]:
    """Why the claim cannot be kept; empty means valid."""
    return list(check_claim(claim, evidences).issues)


@dataclass(frozen=True)
class VerificationReport:
    valid_claims: tuple[Claim, ...]
    issues: dict[str, tuple[str, ...]]  # id_afirmacion -> reasons, only for claims that were dropped
    repaired: tuple[RepairedCitation, ...]


def verify_claims(claims: Iterable[Claim], evidences: Mapping[str, Evidence]) -> VerificationReport:
    valid: list[Claim] = []
    issues: dict[str, tuple[str, ...]] = {}
    repaired: list[RepairedCitation] = []
    for claim in claims:
        checked = check_claim(claim, evidences)
        repaired += checked.repairs
        if checked.issues:
            issues[claim.id_afirmacion] = checked.issues
        else:
            valid.append(checked.claim)
    return VerificationReport(tuple(valid), issues, tuple(repaired))


def verify_case_file(case_file: CaseFile, evidences: Mapping[str, Evidence]) -> VerificationReport:
    return verify_claims(case_file.afirmaciones, evidences)
