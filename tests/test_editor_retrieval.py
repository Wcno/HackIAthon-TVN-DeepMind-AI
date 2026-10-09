import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from whoami import embeddings
from whoami.backend.retrieval import CorpusRetriever


def test_bm25_fallback_searches_news_and_official_evidence():
    evidence = {
        "N-1": {"titulo": "Lluvias en Chiriquí", "campos": {"descripcion": "Inundaciones"}},
        "I-1": {"titulo": "Empleo", "campos": {"valor": "Desempleo juvenil 2025"}},
    }
    retriever = CorpusRetriever(evidence, None)
    assert retriever.search("lluvias chiríquí", 1)[0][0] == "N-1"
    assert retriever.search("desempleo", 1)[0][0] == "I-1"
    assert retriever.search("astronautas", 5) == []
    assert retriever.mode.startswith("bm25")


@pytest.fixture
def local_corpus(tmp_path, monkeypatch):
    model = tmp_path / "model"
    hashes = {}
    for name, relative in {
        "onnx/model_q4.onnx": "onnx/model.onnx",
        "onnx/model_q4.onnx_data": "onnx/model_q4.onnx_data",
        "tokenizer.json": "tokenizer.json",
    }.items():
        path = model / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setenv("WHOAMI_EMBEDDING_MODEL_DIR", str(model))
    directory = tmp_path / "vectors"
    directory.mkdir()
    vectors = np.zeros((3, embeddings.DIMENSIONS), dtype=np.float16)
    vectors[0, 0] = 1
    vectors[1, :2] = [0.5, np.sqrt(0.75)]
    vectors[2, 0] = 1
    path = directory / f"{embeddings.MODEL_NAME}.npy"
    np.save(path, vectors)
    manifest = {
        "modelo": embeddings.MODEL_REPO, "revision": embeddings.MODEL_REVISION,
        "nombre": embeddings.MODEL_NAME, "dimensiones": embeddings.DIMENSIONS,
        "dtype": "float16", "prefijo_documento": embeddings.DOCUMENT_PREFIX,
        "prefijo_consulta": embeddings.QUERY_PREFIX, "receta_texto": embeddings.TEXT_RECIPE,
        "archivos": hashes, "ids": ["N-1", "N-2", "N-not-loaded"],
        "sha256_vectores": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))

    class QueryModel:
        def __init__(self, directory):
            pass

        def embed_queries(self, queries):
            result = np.zeros((len(queries), embeddings.DIMENSIONS), dtype=np.float32)
            result[:, 0] = 1
            return result

    monkeypatch.setattr(embeddings, "Embedder", QueryModel)
    evidence = {
        "N-1": {"titulo": "Precipitaciones", "campos": {}},
        "N-2": {"titulo": "Deportes", "campos": {}},
        "I-1": {"titulo": "Desempleo juvenil", "campos": {}},
    }
    return evidence, directory, model


def test_hybrid_finds_semantic_news_filters_unloaded_ids_and_keeps_official_evidence(local_corpus):
    evidence, directory, _ = local_corpus
    retriever = CorpusRetriever(evidence, directory)
    assert [key for key, _ in retriever.search("lluvias", 10)] == ["N-1"]
    assert "I-1" in [key for key, _ in retriever.search("desempleo", 10)]
    assert retriever.mode.startswith("hybrid")


def test_empty_corpus_and_empty_evidence_texts_have_no_matches():
    for evidence in ({}, {"N-1": {"titulo": "", "campos": {}}}):
        retriever = CorpusRetriever(evidence, None)
        assert retriever.search("lluvias", 5) == []
        assert retriever.search("", 5) == []
        assert retriever.search("lluvias", 0) == []


@pytest.mark.parametrize("damage", ["hash", "revision", "prefix", "dimensions", "ids", "model", "missing"])
def test_unavailable_or_incompatible_assets_degrade_to_lexical_search(local_corpus, damage):
    evidence, directory, model = local_corpus
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if damage == "hash":
        manifest["sha256_vectores"] = "0" * 64
    elif damage == "revision":
        manifest["revision"] = "different"
    elif damage == "prefix":
        manifest["prefijo_consulta"] = "wrong"
    elif damage == "dimensions":
        path = directory / f"{embeddings.MODEL_NAME}.npy"
        np.save(path, np.ones((3, 2), dtype=np.float16))
        manifest["sha256_vectores"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif damage == "ids":
        manifest["ids"] = ["N-1", "N-1", "N-2"]
    elif damage == "model":
        (model / "tokenizer.json").unlink()
    manifest_path.write_text(json.dumps(manifest))
    if damage == "missing":
        manifest_path.unlink()
    retriever = CorpusRetriever(evidence, directory)
    assert [key for key, _ in retriever.search("desempleo", 5)] == ["I-1"]
    assert retriever.search("lluvias", 5) == []
    assert retriever.mode.startswith("bm25:")


def test_inference_failure_keeps_lexical_search_available(local_corpus, monkeypatch):
    evidence, directory, _ = local_corpus

    class BrokenModel:
        def __init__(self, directory):
            pass

        def embed_queries(self, queries):
            raise RuntimeError("local inference unavailable")

    monkeypatch.setattr(embeddings, "Embedder", BrokenModel)
    retriever = CorpusRetriever(evidence, directory)
    assert [key for key, _ in retriever.search("desempleo", 5)] == ["I-1"]
    assert retriever.mode.startswith("bm25:")


def test_concurrent_searches_and_cache_eviction_preserve_results(local_corpus):
    evidence, directory, _ = local_corpus
    retriever = CorpusRetriever(evidence, directory)
    queries = [f"lluvias {number}" for number in range(140)] + ["lluvias 0"] * 10
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda query: retriever.search(query, 1), queries))
    assert all([key for key, _ in result] == ["N-1"] for result in results)
    assert retriever.mode.startswith("hybrid:")


def test_related_keeps_only_evidence_that_contains_every_query_word_without_embeddings():
    evidence = {
        "N-1": {"titulo": "Canal de Panamá aumenta los tránsitos diarios", "campos": {"descripcion": "Desde octubre"}},
        "N-2": {"titulo": "Tránsito vehicular en la capital", "campos": {}},
    }
    retriever = CorpusRetriever(evidence, None)
    assert retriever.related("tránsitos diarios", 5) == ["N-1"]
    assert retriever.related("tránsitos diarios en Marte", 5) == []
    assert retriever.related("receta de sancocho", 5) == []
    assert retriever.related("de la", 5) == []
