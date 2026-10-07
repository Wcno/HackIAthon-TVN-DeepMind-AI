"""Embedding index over every evidence, and the retrievers built on it.

Each evidence is embedded as a natural Spanish sentence (`evidence_text`), not as raw fields: official figures
carry their country, spoken period, value and source, which is what a question about them is phrased with.
The embedder is any object with `embed_queries` and `embed_documents`, so the minimal ONNX one below can be
replaced by another with the same two methods.
"""

import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from whoami.contracts import PROCESSED
from whoami.generation.retrieval import (
    BM25Index,
    BM25Retriever,
    EmbeddingIndex,
    EmbeddingRetriever,
    HybridRetriever,
    Retriever,
    documents_from,
)
from whoami.schemas import Evidence

COUNTRIES = {
    "PAN": "Panamá",
    "CRI": "Costa Rica",
    "COL": "Colombia",
    "DOM": "República Dominicana",
    "MEX": "México",
    "GTM": "Guatemala",
}
SOURCE_NAMES = {"indicador": "Banco Mundial", "serie_inec": "INEC"}
MONTHS = (
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
)
QUARTERS = ("primer", "segundo", "tercer", "cuarto")

DEFAULT_MODEL_DIR = Path.home() / ".cache/whoami/models/local/embeddinggemma-300m-q4"
QUERY_PREFIX = "task: search result | query: "
DOCUMENT_PREFIX = "title: none | text: "
MAX_TOKENS = 512
BATCH_SIZE = 32

VECTORS_CACHE = PROCESSED / "evidencias_vectores.npy"

EmbedTexts = Callable[[Sequence[str]], np.ndarray]


def spanish_period(period: str) -> str:
    """`2026-08` to `agosto de 2026`, `2026-T2` to `segundo trimestre de 2026`; a year stays a year."""
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        return f"{MONTHS[int(period[5:]) - 1]} de {period[:4]}"
    if re.fullmatch(r"\d{4}-T[1-4]", period):
        return f"{QUARTERS[int(period[-1]) - 1]} trimestre de {period[:4]}"
    return period


def _country(evidence: Evidence) -> str:
    if evidence.tipo != "indicador":
        return COUNTRIES["PAN"]
    code = evidence.id_evidencia.split("-")[1]
    return COUNTRIES.get(code, code)


def evidence_text(evidence: Evidence) -> str:
    """The sentence an evidence is embedded as."""
    fields = evidence.campos
    if evidence.tipo == "noticia":
        title, description = fields["titulo"], fields.get("descripcion", "")
        return f"{title}. {description}" if description else title
    if evidence.tipo == "sismo":
        return f"Sismo de magnitud {fields['valor']} en {fields['lugar']}, {fields['periodo']} (USGS)"
    name = fields.get("indicador") or fields["serie"]
    return (
        f"{name} de {_country(evidence)} en {spanish_period(fields['periodo'])}: "
        f"{fields['valor']} {fields['unidad']} ({SOURCE_NAMES[evidence.tipo]})"
    )


class Embedder(Protocol):
    def embed_queries(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...


def model_dir() -> Path:
    return Path(os.environ.get("WHOAMI_EMBEDDING_MODEL_DIR") or DEFAULT_MODEL_DIR)


class OnnxEmbedder:
    """EmbeddingGemma (q4) on CPU. Output is the model's `sentence_embedding`, L2-normalized."""

    def __init__(self, directory: Path | None = None) -> None:
        import onnxruntime
        from tokenizers import Tokenizer

        directory = directory or model_dir()
        self._session = onnxruntime.InferenceSession(str(directory / "onnx/model.onnx"), providers=["CPUExecutionProvider"])
        self._tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self._tokenizer.enable_padding()
        self._tokenizer.enable_truncation(MAX_TOKENS)

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        batches = []
        for start in range(0, len(texts), BATCH_SIZE):
            encoded = self._tokenizer.encode_batch(list(texts[start : start + BATCH_SIZE]))
            inputs = {
                "input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64),
            }
            batches.append(self._session.run(["sentence_embedding"], inputs)[0])
        vectors = np.concatenate(batches)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed([QUERY_PREFIX + text for text in texts])

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed([DOCUMENT_PREFIX + text for text in texts])


def build_index(
    evidences: Iterable[Evidence], embed_documents: EmbedTexts, cache_path: Path
) -> tuple[list[str], np.ndarray]:
    """Ids and vectors of every evidence. `cache_path` (`.npy`) and a JSON list of ids beside it are reused
    while the ids are the same and rebuilt otherwise."""
    evidences = list(evidences)
    ids = [evidence.id_evidencia for evidence in evidences]
    ids_path = cache_path.with_suffix(".json")
    if cache_path.exists() and ids_path.exists() and json.loads(ids_path.read_text(encoding="utf-8")) == ids:
        return ids, np.load(cache_path)
    vectors = np.asarray(embed_documents([evidence_text(evidence) for evidence in evidences]))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache_path, vectors)
    ids_path.write_text(json.dumps(ids), encoding="utf-8")
    return ids, vectors


def default_retrievers(
    evidences: Iterable[Evidence], embedder: Embedder | None = None, cache_path: Path = VECTORS_CACHE
) -> dict[str, Retriever]:
    """`bm25`, `emb` and `hybrid` (their reciprocal rank fusion) over the same evidences."""
    evidences = list(evidences)
    embedder = embedder or OnnxEmbedder()
    ids, vectors = build_index(evidences, embedder.embed_documents, cache_path)
    bm25 = BM25Retriever(BM25Index(documents_from(evidences)))
    emb = EmbeddingRetriever(EmbeddingIndex(ids, vectors, lambda query: embedder.embed_queries([query])[0]))
    return {"bm25": bm25, "emb": emb, "hybrid": HybridRetriever([bm25, emb])}
