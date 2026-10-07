"""Local embedding model (bake-off winner): EmbeddingGemma 300M, ONNX q4 build, run on CPU.

The same model embeds the corpus (`whoami embed`) and, later, user queries, so both live behind `Embedder`.
"""

import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np

MODEL_REPO: Final = "onnx-community/embeddinggemma-300m-ONNX"
MODEL_REVISION: Final = "5090578d9565bb06545b4552f76e6bc2c93e4a66"
MODEL_FILES: Final = ("onnx/model_q4.onnx", "onnx/model_q4.onnx_data", "tokenizer.json")
MODEL_NAME: Final = "embeddinggemma-300m-q4"
DIMENSIONS: Final = 768
QUERY_PREFIX: Final = "task: search result | query: "
DOCUMENT_PREFIX: Final = "title: none | text: "
TEXT_RECIPE: Final = "titulo + '. ' + descripcion (si hay descripción); si no, titulo"

MAX_TOKENS: Final = 512
BATCH_SIZE: Final = 32
MODELS_CACHE: Final = Path.home() / ".cache" / "whoami" / "models"

#: Where each downloaded file goes. The ONNX graph references its data file by name, so that one keeps it.
_LAYOUT: Final = {
    "onnx/model_q4.onnx": "onnx/model.onnx",
    "onnx/model_q4.onnx_data": "onnx/model_q4.onnx_data",
    "tokenizer.json": "tokenizer.json",
}

Download = Callable[..., str]


def model_dir() -> Path:
    override = os.environ.get("WHOAMI_EMBEDDING_MODEL_DIR")
    return Path(override) if override else MODELS_CACHE / "local" / MODEL_NAME


def fetch_model(target: Path | None = None, download: Download | None = None) -> Path:
    """Downloads the pinned files (network) into `target`; files already there are kept."""
    if download is None:
        from huggingface_hub import hf_hub_download as download
    target = target or model_dir()
    for filename, destination in _LAYOUT.items():
        path = target / destination
        if path.exists():
            continue
        cached = download(MODEL_REPO, filename, revision=MODEL_REVISION, cache_dir=MODELS_CACHE)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, path)
    return target


def document_text(row: Mapping[str, str]) -> str:
    """The text that represents a news item: the recipe in `TEXT_RECIPE`."""
    description = row.get("descripcion", "")
    return f"{row['titulo']}. {description}" if description else row["titulo"]


class Embedder:
    """`embed_documents` and `embed_queries` return L2-normalized float32 `(n, 768)` matrices.

    `session` and `tokenizer` are injectable so tests never load the real model.
    """

    def __init__(self, directory: Path | None = None, *, session: Any = None, tokenizer: Any = None) -> None:
        directory = directory or model_dir()
        self._session = session or self._load_session(directory / "onnx" / "model.onnx")
        self._tokenizer = tokenizer or self._load_tokenizer(directory / "tokenizer.json")

    @staticmethod
    def _load_session(path: Path) -> Any:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        if threads := os.environ.get("WHOAMI_EMBEDDING_THREADS"):
            options.intra_op_num_threads = int(threads)
        return onnxruntime.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])

    @staticmethod
    def _load_tokenizer(path: Path) -> Any:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(path))
        tokenizer.enable_padding(pad_id=tokenizer.token_to_id("<pad>") or 0, pad_token="<pad>")
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        return tokenizer

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(DOCUMENT_PREFIX, texts)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(QUERY_PREFIX, texts)

    def _embed(self, prefix: str, texts: Sequence[str]) -> np.ndarray:
        batches = [self._embed_batch([prefix + t for t in texts[start : start + BATCH_SIZE]]) for start in range(0, len(texts), BATCH_SIZE)]
        if not batches:
            return np.empty((0, DIMENSIONS), dtype=np.float32)
        return np.concatenate(batches)

    def _embed_batch(self, texts: list[str]) -> np.ndarray:
        encodings = self._tokenizer.encode_batch(texts)
        feed = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
        }
        vectors = np.asarray(self._session.run(["sentence_embedding"], feed)[0], dtype=np.float32)
        return vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
