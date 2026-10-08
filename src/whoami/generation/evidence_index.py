"""Embedding index over every evidence, and the retrievers built on it.

Each evidence is embedded as a natural Spanish sentence (`evidence_text`), not as raw fields: official figures
carry their country, spoken period, value and source, which is what a question about them is phrased with.
The embedder is any object with `embed_queries` and `embed_documents`, so the minimal ONNX one below can be
replaced by another with the same two methods.
"""

import json
import hashlib
import re
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from whoami.contracts import PROCESSED
from whoami.embeddings import Embedder as LocalEmbedder
from whoami.embeddings import model_dir  # noqa: F401  (re-exported for callers of this module)
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


def build_index(
    evidences: Iterable[Evidence], embed_documents: EmbedTexts, cache_path: Path,
    *, model_identity: str | None = None,
) -> tuple[list[str], np.ndarray]:
    """Ids and vectors of every evidence. `cache_path` (`.npy`) and a JSON list of ids beside it are reused
    while the ids are the same and rebuilt otherwise."""
    evidences = list(evidences)
    ids = [evidence.id_evidencia for evidence in evidences]
    texts = [evidence_text(evidence) for evidence in evidences]
    from whoami.embeddings import MODEL_NAME, MODEL_REVISION, DOCUMENT_PREFIX
    identity = model_identity or f"{MODEL_NAME}:{MODEL_REVISION}:{DOCUMENT_PREFIX}:evidence-text-v1"
    fingerprint = hashlib.sha256(json.dumps([identity, ids, texts], ensure_ascii=False).encode("utf-8")).hexdigest()
    ids_path = cache_path.with_suffix(".json")
    metadata_path = cache_path.with_suffix(".metadata.json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if json.loads(ids_path.read_text(encoding="utf-8")) == ids and metadata["fingerprint"] == fingerprint:
            vectors = np.load(cache_path, allow_pickle=False)
            if (vectors.shape == (len(ids), metadata["dimensions"]) and np.isfinite(vectors).all()
                    and hashlib.sha256(cache_path.read_bytes()).hexdigest() == metadata["sha256"]):
                return ids, vectors
    except (OSError, ValueError, KeyError, TypeError):
        pass
    vectors = np.asarray(embed_documents(texts))
    if vectors.ndim != 2 or vectors.shape[0] != len(ids) or not np.isfinite(vectors).all():
        raise ValueError("Evidence embeddings must be a finite matrix with one row per source")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache_path, vectors)
    ids_path.write_text(json.dumps(ids), encoding="utf-8")
    metadata_path.write_text(json.dumps({"fingerprint": fingerprint, "dimensions": vectors.shape[1],
        "sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest()}), encoding="utf-8")
    return ids, vectors


def default_retrievers(
    evidences: Iterable[Evidence], embedder: Embedder | None = None, cache_path: Path = VECTORS_CACHE
) -> dict[str, Retriever]:
    """`bm25`, `emb` and `hybrid` (their reciprocal rank fusion) over the same evidences."""
    evidences = list(evidences)
    embedder = embedder or LocalEmbedder()
    ids, vectors = build_index(evidences, embedder.embed_documents, cache_path)
    bm25 = BM25Retriever(BM25Index(documents_from(evidences)))
    emb = EmbeddingRetriever(EmbeddingIndex(ids, vectors, lambda query: embedder.embed_queries([query])[0]))
    return {"bm25": bm25, "emb": emb, "hybrid": HybridRetriever([bm25, emb])}
