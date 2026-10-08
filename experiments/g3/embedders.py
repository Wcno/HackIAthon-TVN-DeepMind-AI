"""Uniform loader for the local embedding candidates of the bake-off (step 0)."""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODELS_DIR = Path.home() / ".cache/whoami/models"
LOCAL_DIR = MODELS_DIR / "local"
os.environ.setdefault("FASTEMBED_CACHE_PATH", str(MODELS_DIR))
os.environ.setdefault("HF_HUB_CACHE", str(MODELS_DIR))
os.environ.setdefault("HF_HUB_OFFLINE", "1")


@dataclass(frozen=True)
class Candidate:
    key: str
    hf_name: str
    query_prefix: str = ""
    passage_prefix: str = ""
    loader: str = "fastembed"  # fastembed | model2vec | e5small
    local_path: str | None = None
    jina_v3: bool = False


CANDIDATES = {
    c.key: c
    for c in (
        Candidate("minilm", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        Candidate("mpnet", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"),
        Candidate("potion_onnx", "minishlab/potion-multilingual-128M"),
        Candidate("potion_m2v", "minishlab/potion-multilingual-128M", loader="model2vec"),
        Candidate("jina_v2_es", "jinaai/jina-embeddings-v2-base-es"),
        Candidate("e5_small", "intfloat/multilingual-e5-small", "query: ", "passage: ", loader="e5small"),
        Candidate("e5_large", "intfloat/multilingual-e5-large", "query: ", "passage: ", local_path="multilingual-e5-large"),
        Candidate(
            "gemma300m",
            "google/embeddinggemma-300m",
            "task: search result | query: ",
            "title: none | text: ",
            local_path="embeddinggemma-300m",
        ),
        Candidate(
            "gemma300m_q8",
            "google/embeddinggemma-300m",
            "task: search result | query: ",
            "title: none | text: ",
            local_path="embeddinggemma-300m-q8",
        ),
        Candidate(
            "gemma300m_q4",
            "google/embeddinggemma-300m",
            "task: search result | query: ",
            "title: none | text: ",
            local_path="embeddinggemma-300m-q4",
        ),
        Candidate(
            "qwen3_06b_q",
            "Qwen/Qwen3-Embedding-0.6B-Q",
            "Instruct: Dada una consulta, recupera titulares de noticias relevantes\nQuery:",
            "",
        ),
        Candidate("jina_v3", "jinaai/jina-embeddings-v3", local_path="jina-embeddings-v3", jina_v3=True),
    )
}

Embed = Callable[[Sequence[str], bool], np.ndarray]


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    return vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)


def load(key: str, threads: int | None = None, gpu: bool = False) -> Embed:
    """Returns `embed(texts, is_query)` producing L2-normalised float32 vectors."""
    c = CANDIDATES[key]
    if c.loader == "model2vec":
        from model2vec import StaticModel

        snapshot = next((MODELS_DIR / "models--minishlab--potion-multilingual-128M/snapshots").iterdir())
        model = StaticModel.from_pretrained(str(snapshot))
        return lambda texts, is_query: _normalize(model.encode(list(texts)))

    from fastembed import TextEmbedding

    if c.loader == "e5small":
        from fastembed.common.model_description import ModelSource, PoolingType

        if c.hf_name not in {m["model"] for m in TextEmbedding.list_supported_models()}:
            TextEmbedding.add_custom_model(
                model=c.hf_name,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf="intfloat/multilingual-e5-small"),
                dim=384,
                model_file="onnx/model.onnx",
            )
    kwargs = {"cache_dir": str(MODELS_DIR), "threads": threads, "local_files_only": True}
    if gpu:
        kwargs["providers"] = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
    if c.local_path:
        kwargs["specific_model_path"] = str(LOCAL_DIR / c.local_path)
    model = TextEmbedding(c.hf_name, **kwargs)
    embed_providers = _providers(model)

    def embed(texts: Sequence[str], is_query: bool) -> np.ndarray:
        prefix = c.query_prefix if is_query else c.passage_prefix
        texts = [prefix + t for t in texts]
        if c.jina_v3:
            task = 0 if is_query else 1
            return _normalize(np.stack(list(model.embed(texts, batch_size=32, task_id=task))))
        return _normalize(np.stack(list(model.embed(texts, batch_size=32))))

    embed.providers = embed_providers
    return embed


def _providers(model) -> list[str]:
    inner = getattr(model, 'model', None)
    session = getattr(inner, 'model', None)
    return session.get_providers() if hasattr(session, 'get_providers') else []
