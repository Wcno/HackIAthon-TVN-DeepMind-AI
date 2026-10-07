"""Wires the G3 AI components into `run`: hybrid topics and agglomerative grouping, with or without an LLM.

`ai_components(llm, model)` returns the `configure` hook of `run.run`: given the news rows and vectors it builds
the `classify` and `group` the pipeline injects. With `llm=None` nothing leaves the machine.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from whoami.pipeline.grouping import SameEventJudge, group_agglomerative, grey_pairs, judge_pairs, unit_vectors
from whoami.pipeline.topics import (
    LABELS_PATH,
    GemmaTopicClassifier,
    HybridTopicClassifier,
    TopicModel,
    load_labeled_vectors,
)

Rows = Sequence[Mapping[str, str]]
Classify = Callable[[Rows, np.ndarray], list[tuple[str, float, str]]]
Group = Callable[[np.ndarray, Sequence[datetime]], list[list[int]]]


class CountingLLM:
    """Delegates to an LLM and counts, per purpose, the calls answered from the cache and those that hit the network."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm
        self._hits: Counter[str] = Counter()
        self._misses: Counter[str] = Counter()

    def complete(self, model: str, messages: list[dict], *, purpose: str, **options: Any) -> Any:
        completion = self._llm.complete(model, messages, purpose=purpose, **options)
        (self._hits if completion.cached else self._misses)[purpose] += 1
        return completion

    def counts(self) -> dict[str, tuple[int, int]]:
        """`{purpose: (cache hits, cache misses)}`."""
        return {purpose: (self._hits[purpose], self._misses[purpose]) for purpose in sorted(self._hits | self._misses)}


def ai_components(
    llm: Any | None, model: str, labels_path: Path = LABELS_PATH
) -> Callable[[Rows, np.ndarray], tuple[Classify, Group]]:
    def configure(rows: Rows, vectors: np.ndarray) -> tuple[Classify, Group]:
        unit = unit_vectors(vectors)

        def classify(batch_rows: Rows, batch_vectors: np.ndarray) -> list[tuple[str, float, str]]:
            labeled_vectors, labels = load_labeled_vectors(labels_path, rows, unit)
            topic_model = TopicModel.fit(labeled_vectors, labels)
            gemma = GemmaTopicClassifier(llm, model) if llm is not None else None
            return HybridTopicClassifier(topic_model, gemma)(batch_rows, batch_vectors)

        def group(batch_vectors: np.ndarray, dates: Sequence[datetime]) -> list[list[int]]:
            overrides = None
            if llm is not None:
                overrides = judge_pairs(SameEventJudge(llm, model), rows, grey_pairs(batch_vectors, dates))
            return group_agglomerative(batch_vectors, dates, overrides=overrides)

        return classify, group

    return configure
