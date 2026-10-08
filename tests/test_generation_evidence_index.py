"""The text each evidence is embedded as, and the cached vector index over the whole corpus."""

import json

import numpy as np
import pytest

from generation_fakes import news
from whoami.generation.evidence_index import (
    LocalEmbedder,
    build_index,
    default_retrievers,
    evidence_text,
    model_dir,
    spanish_period,
)
from whoami.schemas import Evidence


def official(id_: str, tipo: str, **fields: str) -> Evidence:
    return Evidence(id_evidencia=id_, tipo=tipo, titulo="Titulo", url="https://x.invalid", fecha=None, campos=fields)


@pytest.mark.parametrize(
    ("period", "spoken"),
    [
        ("2026-08", "agosto de 2026"),
        ("2026-01", "enero de 2026"),
        ("2026-T2", "segundo trimestre de 2026"),
        ("2025-T4", "cuarto trimestre de 2025"),
        ("2024", "2024"),
    ],
)
def test_spanish_period(period, spoken):
    assert spanish_period(period) == spoken


def test_news_text_is_title_and_description():
    evidence = news("N-1", titulo="Sube el desempleo", descripcion="Según el INEC")
    assert evidence_text(evidence) == "Sube el desempleo. Según el INEC"


def test_news_text_without_description_is_just_the_title():
    assert evidence_text(news("N-1", titulo="Sube el desempleo")) == "Sube el desempleo"


@pytest.mark.parametrize(
    ("code", "country"),
    [
        ("PAN", "Panamá"),
        ("CRI", "Costa Rica"),
        ("COL", "Colombia"),
        ("DOM", "República Dominicana"),
        ("MEX", "México"),
        ("GTM", "Guatemala"),
    ],
)
def test_world_bank_text_names_the_country_from_the_id(code, country):
    evidence = official(
        f"WB-{code}-SL.UEM.TOTL.ZS-2024", "indicador", indicador="Desempleo", periodo="2024", valor="7,4", unidad="% anual"
    )
    assert evidence_text(evidence) == f"Desempleo de {country} en 2024: 7,4 % anual (Banco Mundial)"


def test_inec_text_is_panama_with_a_spoken_period():
    evidence = official(
        "INEC-ipc-2026-08", "serie_inec", serie="Inflación interanual", periodo="2026-08", valor="2,20", unidad="% interanual"
    )
    assert evidence_text(evidence) == "Inflación interanual de Panamá en agosto de 2026: 2,20 % interanual (INEC)"


def test_quake_text_is_a_sentence_with_magnitude_and_place():
    evidence = official(
        "USGS-us6000rvkl", "sismo", lugar="148 km SSE of Burica, Panama", periodo="2025-12-17", valor="5,6", unidad="magnitud"
    )
    assert evidence_text(evidence) == "Sismo de magnitud 5,6 en 148 km SSE of Burica, Panama, 2025-12-17 (USGS)"


class CountingEmbedder:
    """Deterministic fake: a vector per text from its length, so equal texts give equal vectors."""

    cache_identity = "test-length-and-codepoints-v1"
    dimensions = 3

    def __init__(self) -> None:
        self.documents: list[str] = []
        self.queries: list[str] = []

    @staticmethod
    def _vectors(texts) -> np.ndarray:
        return np.array([[len(t), 1.0, sum(map(ord, t)) % 7] for t in texts], dtype=np.float64)

    def embed_documents(self, texts):
        self.documents += list(texts)
        return self._vectors(texts)

    def embed_queries(self, texts):
        self.queries += list(texts)
        return self._vectors(texts)


EVIDENCES = {e.id_evidencia: e for e in (news("N-1", titulo="Canal de Panamá"), news("N-2", titulo="Sismo en Chiriquí"))}


def test_build_index_embeds_every_evidence_and_writes_the_cache(tmp_path):
    embedder = CountingEmbedder()
    cache = tmp_path / "vectors.npy"
    ids, vectors = build_index(list(EVIDENCES.values()), embedder.embed_documents, cache)
    assert ids == ["N-1", "N-2"] and vectors.shape == (2, 3)
    assert embedder.documents == ["Canal de Panamá", "Sismo en Chiriquí"]
    assert cache.exists() and json.loads(cache.with_suffix(".json").read_text(encoding="utf-8")) == ["N-1", "N-2"]


def test_build_index_reuses_the_cache_when_the_ids_match(tmp_path):
    embedder = CountingEmbedder()
    cache = tmp_path / "vectors.npy"
    first = build_index(list(EVIDENCES.values()), embedder.embed_documents, cache)
    again = build_index(list(EVIDENCES.values()), embedder.embed_documents, cache)
    assert len(embedder.documents) == 2
    assert again[0] == first[0] and np.array_equal(again[1], first[1])


def test_build_index_rebuilds_when_the_ids_differ(tmp_path):
    embedder = CountingEmbedder()
    cache = tmp_path / "vectors.npy"
    build_index(list(EVIDENCES.values()), embedder.embed_documents, cache)
    extra = [*EVIDENCES.values(), news("N-3", titulo="Nuevo")]
    ids, vectors = build_index(extra, embedder.embed_documents, cache)
    assert ids == ["N-1", "N-2", "N-3"] and len(vectors) == 3
    assert len(embedder.documents) == 5


def test_build_index_rebuilds_same_ids_when_content_or_model_changes(tmp_path):
    embedder = CountingEmbedder()
    cache = tmp_path / "vectors.npy"
    sources = [news("N-1", titulo="Canal")]
    build_index(sources, embedder.embed_documents, cache)
    build_index([news("N-1", titulo="Hospital")], embedder.embed_documents, cache)
    assert embedder.documents == ["Canal", "Hospital"]


def test_model_change_and_corrupt_cache_are_rebuilt(tmp_path):
    embedder = CountingEmbedder()
    cache = tmp_path / "vectors.npy"
    sources = [news("N-1", titulo="Canal")]
    build_index(sources, embedder.embed_documents, cache, model_identity="model-a")
    build_index(sources, embedder.embed_documents, cache, model_identity="model-b")
    assert len(embedder.documents) == 2
    cache.write_bytes(b"")
    build_index(sources, embedder.embed_documents, cache, model_identity="model-b")
    assert len(embedder.documents) == 3


def test_default_retrievers_use_the_actual_encoder_identity(tmp_path):
    first, second = CountingEmbedder(), CountingEmbedder()
    second.cache_identity = "test-replacement-encoder-v2"
    cache = tmp_path / "vectors.npy"
    default_retrievers(EVIDENCES.values(), first, cache)
    default_retrievers(EVIDENCES.values(), second, cache)
    assert second.documents == ["Canal de Panamá", "Sismo en Chiriquí"]


def test_encoder_dimension_change_invalidates_the_cached_matrix(tmp_path):
    encoder = CountingEmbedder()
    cache = tmp_path / "vectors.npy"
    build_index(EVIDENCES.values(), encoder.embed_documents, cache)
    encoder.dimensions = 2
    encoder.embed_documents = lambda texts: np.ones((len(texts), 2))
    _, vectors = build_index(EVIDENCES.values(), encoder.embed_documents, cache,
                             model_identity=encoder.cache_identity, expected_dimensions=2)
    assert vectors.shape == (2, 2)


def test_opaque_encoders_cannot_silently_reuse_another_encoders_vectors(tmp_path):
    cache = tmp_path / "vectors.npy"
    build_index(EVIDENCES.values(), lambda texts: np.ones((len(texts), 2)), cache)
    _, vectors = build_index(EVIDENCES.values(), lambda texts: np.zeros((len(texts), 2)), cache)
    assert not vectors.any()


def test_default_retrievers_offers_bm25_embeddings_and_hybrid(tmp_path):
    embedder = CountingEmbedder()
    retrievers = default_retrievers(list(EVIDENCES.values()), embedder, tmp_path / "vectors.npy")
    assert set(retrievers) == {"bm25", "emb", "hybrid"}
    hits = retrievers["emb"].search("Canal de Panamá", 2)
    assert hits[0][0] == "N-1" and hits[0][1] == pytest.approx(1.0)
    assert embedder.queries == ["Canal de Panamá"]
    assert retrievers["hybrid"].search("Canal de Panamá", 2)[0][0] == "N-1"


@pytest.mark.skipif(not model_dir().exists(), reason="local embedding model not downloaded")
def test_onnx_embedder_ranks_the_related_sentence_first_with_unit_vectors():
    embedder = LocalEmbedder()
    query = embedder.embed_queries(["¿Cuál es la tasa de desempleo de Panamá?"])[0]
    documents = embedder.embed_documents(
        ["Desempleo de Panamá en 2024: 7,4 % anual (Banco Mundial)", "Sismo de magnitud 5,6 en Burica (USGS)"]
    )
    assert np.linalg.norm(query) == pytest.approx(1.0, abs=1e-4)
    assert (documents @ query).argmax() == 0
