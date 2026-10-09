from whoami.backend.live_queries import _CorpusGate


class FakeCorpus:
    def __init__(self, related: list[str]) -> None:
        self.found = related

    def related(self, query: str, k: int) -> list[str]:
        return self.found[:k]


def test_a_query_with_related_evidence_reaches_the_model():
    assert _CorpusGate(FakeCorpus(["N-1"])).decide("tránsitos diarios").answerable


def test_a_query_without_related_evidence_abstains_before_the_model():
    decision = _CorpusGate(FakeCorpus([])).decide("receta de sancocho")
    assert not decision.answerable
    assert decision.motivo
