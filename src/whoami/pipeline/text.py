"""Text helpers shared by the pipeline rules."""

import re
import unicodedata


def fold(text: str) -> str:
    """Lowercase without accents, so `Panamá` and `PANAMA` compare equal."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def word_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Matches any term as a whole word or phrase."""
    return re.compile(r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b")
