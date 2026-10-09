import pytest

from whoami.backend.live_queries import FREE_TEXT_MIN_COSINE, _CorpusGate
from whoami.generation.prompting import MIN_COSINE


class FakeCorpus:
    def __init__(self, best: float | None) -> None:
        self.best = best

    def cosine_search(self, query: str, k: int):
        return None if self.best is None else [("N-1", self.best)][:k]


@pytest.mark.parametrize("best", [0.467, 0.506, 0.591])
def test_free_text_keywords_below_the_batch_threshold_reach_the_model(best):
    assert best < MIN_COSINE
    assert _CorpusGate(FakeCorpus(best)).decide("precio del combustible").answerable


@pytest.mark.parametrize("best", [0.225, 0.302, 0.386])
def test_off_topic_and_injection_probes_still_abstain(best):
    decision = _CorpusGate(FakeCorpus(best)).decide("¿Quién ganó el Mundial de 1986?")
    assert not decision.answerable
    assert decision.motivo


def test_threshold_sits_between_off_topic_and_on_topic_measurements():
    assert 0.386 < FREE_TEXT_MIN_COSINE < 0.464


def test_without_embeddings_the_verifier_is_the_safeguard():
    assert _CorpusGate(FakeCorpus(None)).decide("cualquier cosa").answerable
