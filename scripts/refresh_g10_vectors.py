"""Prepare G10 vectors, reusing only byte-verified vectors for exactly unchanged inputs.

The original G3 snapshot pins its input CSV, vector hash, model files and recipe in
one Git commit. This avoids repeating inference on 2,844 unchanged news articles.
No model is needed during the subsequent offline demonstration.
"""

import csv
import hashlib
import io
import json
import os
import subprocess

import numpy as np

from whoami import embeddings
from whoami.contracts import PROCESSED
from whoami.pipeline.evidence import load_news_rows

SOURCE_COMMIT = "f7a1dd204aa05d7e69ae6853cc93408290cd8e30"


def saved(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_COMMIT}:{path}"])


def main() -> None:
    directory = "data/processed/embeddings/"
    previous = json.loads(saved(directory + "manifest.json"))
    raw_vectors = saved(directory + f"{embeddings.MODEL_NAME}.npy")
    if hashlib.sha256(raw_vectors).hexdigest() != previous["sha256_vectores"]:
        raise ValueError("Historical vectors failed their recorded hash")
    expected = {"modelo": embeddings.MODEL_REPO, "revision": embeddings.MODEL_REVISION,
                "dimensiones": embeddings.DIMENSIONS, "dtype": "float16", "receta_texto": embeddings.TEXT_RECIPE,
                "prefijo_documento": embeddings.DOCUMENT_PREFIX, "prefijo_consulta": embeddings.QUERY_PREFIX}
    if any(previous.get(key) != value for key, value in expected.items()):
        raise ValueError("The historical model and text recipe are incompatible")
    old_vectors = np.load(io.BytesIO(raw_vectors), allow_pickle=False)
    if old_vectors.shape != (len(previous["ids"]), embeddings.DIMENSIONS) or not np.isfinite(old_vectors).all():
        raise ValueError("Invalid historical vectors")
    old_rows = {row["id_noticia"]: row for row in csv.DictReader(io.StringIO(saved("data/processed/noticias.csv").decode("utf-8")))}
    old_positions = {key: position for position, key in enumerate(previous["ids"])}
    rows = load_news_rows()
    reused = {position: old_positions[row["id_noticia"]] for position, row in enumerate(rows)
              if row["id_noticia"] in old_positions and row["id_noticia"] in old_rows
              and embeddings.document_text(row) == embeddings.document_text(old_rows[row["id_noticia"]])}
    missing = [position for position in range(len(rows)) if position not in reused]
    os.environ.setdefault("WHOAMI_EMBEDDING_THREADS", "2")
    model = embeddings.Embedder()
    layout = {"onnx/model_q4.onnx": "onnx/model.onnx", "onnx/model_q4.onnx_data": "onnx/model_q4.onnx_data",
              "tokenizer.json": "tokenizer.json"}
    for name, local in layout.items():
        with (embeddings.model_dir() / local).open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != previous["archivos"][name]:
                raise ValueError("The installed model differs from the historical snapshot")

    class RefreshedCorpus:
        def embed_documents(self, texts):
            if texts != [embeddings.document_text(row) for row in rows]:
                raise ValueError("Input order changed during the refresh")
            result = np.empty((len(rows), embeddings.DIMENSIONS), dtype=np.float32)
            for position, old in reused.items():
                result[position] = old_vectors[old]
            # Short batches bound padding when a few new excerpts are much longer than headlines.
            for start in range(0, len(missing), 8):
                positions = missing[start:start + 8]
                result[positions] = model.embed_documents([texts[position] for position in positions])
                print(f"computed {min(start + 8, len(missing))}/{len(missing)}; reused {len(reused)}", flush=True)
            return result

    embeddings.embed_corpus(rows, RefreshedCorpus(), PROCESSED / "embeddings")
    path = PROCESSED / "embeddings/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["refresh"] = {"source_commit": SOURCE_COMMIT, "source_vector_sha256": previous["sha256_vectores"],
                           "reused_identical_documents": len(reused), "computed_documents": len(missing)}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
