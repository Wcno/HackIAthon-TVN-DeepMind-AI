"""The text each evidence is embedded as, and the cached vector index over the whole corpus."""

import json

import numpy as np
import pytest

from generation_fakes import news
from whoami.generation.evidence_index import (
    OnnxEmbedder,
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
    assert cache.exists() and json.loads(cache.with_suffix(".json").read_text()) == ["N-1", "N-2"]


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
    embedder = OnnxEmbedder()
    query = embedder.embed_queries(["¿Cuál es la tasa de desempleo de Panamá?"])[0]
    documents = embedder.embed_documents(
        ["Desempleo de Panamá en 2024: 7,4 % anual (Banco Mundial)", "Sismo de magnitud 5,6 en Burica (USGS)"]
    )
    assert np.linalg.norm(query) == pytest.approx(1.0, abs=1e-4)
    assert (documents @ query).argmax() == 0
