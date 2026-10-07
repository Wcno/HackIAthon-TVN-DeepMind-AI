"""Who produced the content (CU-03): an agency story republished by three outlets is one provenance."""

import re
from collections.abc import Sequence

from whoami.pipeline.text import fold
from whoami.schemas import Member

AGENCIES = ("EFE", "AFP", "Reuters", "AP", "Europa Press", "ANSA", "DPA", "Xinhua")

#: Case-sensitive whole words: `AP` and `EFE` would otherwise match inside ordinary words.
_AGENCY_PATTERN = re.compile(r"\b(" + "|".join(re.escape(agency) for agency in AGENCIES) + r")\b")

#: Two headlines this similar (token-set Jaccard) tell the same story with the same words.
NEAR_IDENTICAL_THRESHOLD = 0.8

#: Function words carry no story; removing them stops "de la" from inflating the overlap.
_STOPWORDS = frozenset(
    "a al ante bajo con contra de del desde durante e el ella ellas ellos en entre es ese esa esos esas esta este "
    "estas estos ha han hay la las le les lo los mas me mi muy ni no nos o para pero por que se sin sobre son su sus "
    "te tras tu un una uno unas unos y ya".split()
)

_TRAILING_OUTLET = re.compile(r"\s*\([^)]*\)\s*$")
_TOKEN = re.compile(r"[a-z0-9]+")


def detect_agency(row: dict) -> str | None:
    match = _AGENCY_PATTERN.search(f"{row['titulo']}\n{row.get('descripcion', '')}")
    return match.group(1) if match else None


def provenance(row: dict) -> str:
    """The agency if the item names one, else its outlet."""
    return detect_agency(row) or row["medio"]


def _tokens(text: str) -> set[str]:
    folded = fold(_TRAILING_OUTLET.sub("", text))
    return set(_TOKEN.findall(folded)) - _STOPWORDS


def near_identical(a: str, b: str) -> bool:
    tokens_a, tokens_b = _tokens(a), _tokens(b)
    union = tokens_a | tokens_b
    return bool(union) and len(tokens_a & tokens_b) / len(union) >= NEAR_IDENTICAL_THRESHOLD


def merge_provenances(members: Sequence[Member]) -> list[Member]:
    """A member near-identical to an earlier one from another outlet takes that member's provenance.

    A press release copied by an outlet is one origin. Returns new members in the original order.
    """
    by_date = sorted(range(len(members)), key=lambda index: members[index].fecha_publicacion)
    resolved: dict[int, str] = {}
    for position, index in enumerate(by_date):
        current = members[index]
        resolved[index] = current.procedencia
        for earlier_index in by_date[:position]:
            earlier = members[earlier_index]
            if earlier.medio != current.medio and near_identical(earlier.titulo, current.titulo):
                resolved[index] = resolved[earlier_index]
                break
    return [member.model_copy(update={"procedencia": resolved[index]}) for index, member in enumerate(members)]
