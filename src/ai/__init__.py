"""AI capabilities used by the editorial prototype."""

from .classifier import (
    Classification,
    ClassificationError,
    classify_with_gemini,
    keyword_baseline,
)

__all__ = [
    "Classification",
    "ClassificationError",
    "classify_with_gemini",
    "keyword_baseline",
]
