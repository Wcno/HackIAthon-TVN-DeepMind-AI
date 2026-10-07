"""The cosine gate decides on the embedding score of the query, whatever retriever feeds the answer."""

import pytest

from whoami.generation.prompting import MIN_COSINE, CosineGate


class FixedRetriever:
    def __init__(self, hits: list[tuple[str, float]]) -> None:
        self._hits = hits
        self.queries: list[str] = []

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        self.queries.append(query)
        return self._hits[:k]


def test_the_threshold_is_the_measured_one():
    assert MIN_COSINE == 0.62


@pytest.mark.parametrize(("cosine", "answerable"), [(0.629, True), (0.62, True), (0.619, False), (0.3, False)])
def test_answerable_when_the_top_cosine_reaches_the_threshold(cosine, answerable):
    gate = CosineGate(FixedRetriever([("N-1", cosine), ("N-2", 0.1)]))
    assert gate.decide("¿Cuánto cayó el desempleo?", hits=[]).answerable is answerable


def test_it_ignores_the_hits_of_the_retriever_that_feeds_the_answer():
    gate = CosineGate(FixedRetriever([("N-1", 0.3)]))
    assert not gate.decide("¿?", [("N-9", 99.0)]).answerable


def test_a_refusal_says_why_and_what_is_missing():
    decision = CosineGate(FixedRetriever([("N-1", 0.3)])).decide("¿Quién ganó el partido?", [])
    assert decision.motivo and "¿Quién ganó el partido?" in decision.faltante


def test_no_hits_at_all_is_a_refusal():
    assert not CosineGate(FixedRetriever([])).decide("¿?", []).answerable
