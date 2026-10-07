import numpy as np
import pytest

from generation_fakes import by_id, news
from whoami.generation.retrieval import (
    BM25Index,
    BM25Retriever,
    Document,
    EmbeddingIndex,
    EmbeddingRetriever,
    HybridRetriever,
    documents_from,
    hybrid_rrf,
    tokenize,
)


def test_a_document_is_the_title_and_every_field_value():
    evidence = news("N-1", titulo="Canal limita", descripcion="Por la sequía")
    document = Document.from_evidence(evidence)
    assert document.id_evidencia == "N-1"
    assert document.text == "Titular\nCanal limita\nPor la sequía"


def test_tokens_are_lowercase_accentless_without_stopwords_and_lightly_stemmed():
    assert tokenize("¿Cuántos TRÁNSITOS diarios limitará el Canal de Panamá?") == [
        "transito", "diario", "limitara", "canal", "panama",
    ]  # fmt: skip
    assert tokenize("regulaciones y regulación") == ["regulacion", "regulacion"]
    assert tokenize("ciudades buques crisis mes") == ["ciudad", "buque", "crisis", "mes"]


def test_bm25_score_matches_the_okapi_formula():
    index = BM25Index([Document("d1", "canal canal lago"), Document("d2", "lago sequia")])
    # idf = ln((2 - 1 + .5) / (1 + .5) + 1); tf = 2, dl = 3, avgdl = 2.5, k1 = 1.5, b = .75
    [(found, score)] = index.search("canal", 5)
    assert found == "d1"
    assert score == pytest.approx(0.930398, rel=1e-5)


def test_bm25_ranks_the_relevant_document_first_and_drops_zero_scores():
    index = BM25Index(
        [
            Document("d1", "El Canal limita los tránsitos diarios por la sequía"),
            Document("d2", "Corte de agua en San Miguelito"),
            Document("d3", "Inflación anual de 2,3 %"),
        ]
    )
    results = index.search("¿Cuántos tránsitos diarios limitará el Canal?", 8)
    assert [i for i, _ in results] == ["d1"]
    assert index.search("de la el", 8) == []
    assert index.search("quórum", 8) == []


def test_bm25_respects_k_and_breaks_ties_by_id():
    index = BM25Index([Document(f"d{n}", "canal") for n in (3, 1, 2)])
    assert [i for i, _ in index.search("canal", 2)] == ["d1", "d2"]


def test_bm25_matches_plural_and_accent_variants():
    index = BM25Index([Document("d1", "nueva regulación aprobada")])
    assert [i for i, _ in index.search("regulaciones", 3)] == ["d1"]


VECTORS = np.array([[1.0, 0.0], [0.0, 1.0], [3.0, 3.0]])


def test_embedding_index_returns_cosine_top_k_over_normalized_vectors():
    index = EmbeddingIndex(["a", "b", "c"], VECTORS, lambda query: np.array([5.0, 0.0]))
    results = index.search("lo que sea", 2)
    assert [i for i, _ in results] == ["a", "c"]
    assert results[0][1] == pytest.approx(1.0)
    assert results[1][1] == pytest.approx(np.sqrt(0.5))


def test_embedding_index_survives_a_zero_vector():
    index = EmbeddingIndex(["a", "z"], np.array([[1.0, 0.0], [0.0, 0.0]]), lambda query: np.array([1.0, 0.0]))
    assert [i for i, _ in index.search("q", 5)][0] == "a"


def test_reciprocal_rank_fusion_rewards_agreement():
    fused = hybrid_rrf([["a", "b"], ["b", "c"], ["b", "a"]], k=60)
    assert [i for i, _ in fused] == ["b", "a", "c"]
    assert dict(fused)["b"] == pytest.approx(1 / 62 + 1 / 61 + 1 / 61)
    assert dict(fused)["c"] == pytest.approx(1 / 62)


def test_reciprocal_rank_fusion_of_nothing_is_empty():
    assert hybrid_rrf([]) == []


EVIDENCES = by_id(
    news("N-1", titulo="El Canal limita los tránsitos diarios"),
    news("N-2", titulo="Corte de agua en San Miguelito"),
    news("N-3", titulo="Inflación anual de septiembre"),
)


def test_bm25_retriever_searches_the_evidence_corpus():
    retriever = BM25Retriever(BM25Index(documents_from(EVIDENCES.values())))
    assert retriever.search("tránsitos del Canal", 3)[0][0] == "N-1"


def test_embedding_retriever_delegates_to_its_index():
    index = EmbeddingIndex(["N-1", "N-2"], np.array([[1.0, 0.0], [0.0, 1.0]]), lambda q: np.array([0.0, 1.0]))
    assert EmbeddingRetriever(index).search("agua", 1)[0][0] == "N-2"


def test_hybrid_retriever_fuses_its_members():
    lexical = BM25Retriever(BM25Index(documents_from(EVIDENCES.values())))
    semantic = EmbeddingRetriever(
        EmbeddingIndex(["N-1", "N-2", "N-3"], np.eye(3), lambda q: np.array([0.0, 0.1, 1.0]))
    )
    results = HybridRetriever([lexical, semantic]).search("inflación", 2)
    assert results[0][0] == "N-3"
    assert len(results) == 2
