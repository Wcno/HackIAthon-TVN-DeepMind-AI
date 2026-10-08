"""Text helpers shared by the pipeline rules."""

import re
import unicodedata
from collections.abc import Iterable, Mapping


def fold(text: str) -> str:
    """Lowercase without accents, so `Panamá` and `PANAMA` compare equal."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def word_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Matches any term as a whole word or phrase."""
    return re.compile(r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b")


def rows_text(rows: Iterable[Mapping[str, str]]) -> str:
    """Titles and descriptions of a group's news rows, as one text to match rules against."""
    return "\n".join(f"{row['titulo']}\n{row.get('descripcion', '')}" for row in rows)
