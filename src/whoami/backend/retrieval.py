"""Offline hybrid retrieval over the editor's loaded evidence, with explicit BM25 fallback.

Scores in hybrid mode are reciprocal rank fusion scores, not cosine confidence.
The synchronous search boundary should be offloaded by async HTTP callers.
"""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from threading import RLock

import numpy as np

from whoami import embeddings
from whoami.generation.prompting import MIN_COSINE
from whoami.generation.retrieval import BM25Index, Document, EmbeddingIndex, hybrid_rrf, tokenize
from whoami.pipeline.run import load_vectors

QUERY_CACHE_SIZE = 128
_MODEL_LAYOUT = {
    "onnx/model_q4.onnx": "onnx/model.onnx",
    "onnx/model_q4.onnx_data": "onnx/model_q4.onnx_data",
    "tokenizer.json": "tokenizer.json",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CorpusRetriever:
    """Load verified corpus vectors once; never download or re-embed documents.

    Model initialization, tokenizer access and the bounded query LRU are serialized.
    A failed initialization or inference permanently degrades this instance to BM25.
    """

    def __init__(self, evidence: dict[str, dict], embeddings_directory: Path | None):
        documents = [
            Document(key, "\n".join([item.get("titulo", ""), *item.get("campos", {}).values()]))
            for key, item in evidence.items()
        ]
        self._lexical = BM25Index([document for document in documents if tokenize(document.text)])
        self._ids = set(evidence)
        self._directory = embeddings_directory
        self._lock = RLock()
        self._initialized = embeddings_directory is None
        self._semantic = None
        self._embedder = None
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.mode = "bm25: embeddings unavailable" if embeddings_directory is None else "bm25: local hybrid pending initialization"

    def _initialize(self) -> None:
        self._initialized = True
        directory = self._directory
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "modelo": embeddings.MODEL_REPO,
            "revision": embeddings.MODEL_REVISION,
            "nombre": embeddings.MODEL_NAME,
            "dimensiones": embeddings.DIMENSIONS,
            "dtype": "float16",
            "prefijo_documento": embeddings.DOCUMENT_PREFIX,
            "prefijo_consulta": embeddings.QUERY_PREFIX,
            "receta_texto": embeddings.TEXT_RECIPE,
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ValueError("incompatible embedding manifest")
        ids = manifest["ids"]
        if not isinstance(ids, list) or not all(isinstance(key, str) for key in ids) or len(set(ids)) != len(ids):
            raise ValueError("invalid corpus ids")
        digest = manifest.get("sha256_vectores")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("missing vector hash")
        path = directory / f"{embeddings.MODEL_NAME}.npy"
        vectors = load_vectors(path, [{"id_noticia": key} for key in ids])
        if vectors.shape != (len(ids), embeddings.DIMENSIONS) or vectors.dtype != np.float16:
            raise ValueError("invalid vector dimensions or dtype")
        if not np.isfinite(vectors).all() or np.any(np.linalg.norm(vectors.astype(np.float32), axis=1) == 0):
            raise ValueError("invalid corpus vectors")
        selected = [position for position, key in enumerate(ids) if key in self._ids]
        if not selected:
            raise ValueError("no vectors for loaded evidence")
        model = embeddings.model_dir()
        hashes = manifest["archivos"]
        for name, relative in _MODEL_LAYOUT.items():
            local = model / relative
            if not local.is_file() or _digest(local) != hashes.get(name):
                raise ValueError("local model missing or incompatible")
        self._embedder = embeddings.Embedder(directory=model)
        self._semantic = EmbeddingIndex([ids[position] for position in selected], vectors[selected], self._query_vector)
        self.mode = "hybrid: local embeddinggemma + BM25 (cosine >= 0.62)"

    def _query_vector(self, query: str) -> np.ndarray:
        if query in self._cache:
            self._cache.move_to_end(query)
            return self._cache[query]
        vector = np.asarray(self._embedder.embed_queries([query]), dtype=np.float32)
        if vector.shape != (1, embeddings.DIMENSIONS) or not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
            raise ValueError("invalid query vector")
        self._cache[query] = vector[0]
        if len(self._cache) > QUERY_CACHE_SIZE:
            self._cache.popitem(last=False)
        return vector[0]

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        if k <= 0 or not query.strip():
            return []
        with self._lock:
            lexical = self._lexical.search(query, max(20, k))
            try:
                if not self._initialized:
                    self._initialize()
                if self._semantic is not None:
                    semantic = [key for key, score in self._semantic.search(query, max(20, k)) if score >= MIN_COSINE]
                    return hybrid_rrf([[key for key, _ in lexical], semantic])[:k]
            except Exception as error:
                # Failure details may contain model paths or user content: expose only the type.
                self._semantic = None
                self._embedder = None
                self._cache.clear()
                self.mode = f"bm25: local embeddings unavailable ({type(error).__name__})"
            return lexical[:k]
