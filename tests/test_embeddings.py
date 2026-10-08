import hashlib
import json
import re

import numpy as np
import pytest

from whoami import embeddings
from whoami.pipeline import run
from whoami.pipeline.run import PipelineInputError, default_vectors_path, load_vectors
from whoami.embeddings import (
    DIMENSIONS,
    DOCUMENT_PREFIX,
    MODEL_FILES,
    MODEL_REVISION,
    QUERY_PREFIX,
    Embedder,
    document_text,
    embed_corpus,
    fetch_model,
    model_dir,
)


class FakeEncoding:
    def __init__(self, ids, mask):
        self.ids = ids
        self.attention_mask = mask


class FakeTokenizer:
    """One token per character, padded to the longest text of the batch."""

    def __init__(self):
        self.seen = []

    def encode_batch(self, texts):
        self.seen.append(list(texts))
        width = max(len(t) for t in texts)
        return [FakeEncoding([ord(c) for c in t] + [0] * (width - len(t)), [1] * len(t) + [0] * (width - len(t))) for t in texts]


class FakeSession:
    """The vector of a text is [number of tokens, 1, 0, ...]: scaled, so only normalization makes it a unit vector."""

    def __init__(self):
        self.calls = []

    def run(self, output_names, feed):
        self.calls.append((output_names, feed))
        mask = feed["attention_mask"]
        out = np.zeros((len(mask), DIMENSIONS), dtype=np.float32)
        out[:, 0] = mask.sum(axis=1)
        out[:, 1] = 1.0
        return [out]


def embedder():
    session, tokenizer = FakeSession(), FakeTokenizer()
    return Embedder(session=session, tokenizer=tokenizer), session, tokenizer


def test_documents_and_queries_get_their_own_prefix():
    model, _, tokenizer = embedder()

    model.embed_documents(["hola"])
    model.embed_queries(["hola"])

    assert tokenizer.seen == [[DOCUMENT_PREFIX + "hola"], [QUERY_PREFIX + "hola"]]


def test_vectors_are_float32_unit_length_with_768_dimensions():
    model, _, _ = embedder()

    vectors = model.embed_documents(["uno", "dos tres cuatro"])

    assert vectors.shape == (2, 768)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-6)


def test_the_session_receives_int64_ids_and_mask_and_the_sentence_embedding_is_read():
    model, session, _ = embedder()

    model.embed_documents(["uno", "dos tres"])

    names, feed = session.calls[0]
    assert names == ["sentence_embedding"]
    assert set(feed) == {"input_ids", "attention_mask"}
    assert feed["input_ids"].dtype == np.int64
    assert feed["attention_mask"].dtype == np.int64
    assert feed["input_ids"].shape == feed["attention_mask"].shape


def test_texts_are_embedded_in_batches_of_32_and_keep_their_order():
    model, session, _ = embedder()
    texts = ["x" * (n + 1) for n in range(70)]

    vectors = model.embed_documents(texts)

    assert [len(feed["input_ids"]) for _, feed in session.calls] == [32, 32, 6]
    lengths = [len(DOCUMENT_PREFIX) + n + 1 for n in range(70)]
    expected_ratio = np.array(lengths) / 1.0
    assert np.allclose(vectors[:, 0] / vectors[:, 1], expected_ratio, rtol=1e-4)


def test_no_texts_give_an_empty_matrix():
    model, session, _ = embedder()

    assert model.embed_documents([]).shape == (0, 768)
    assert session.calls == []


def test_the_text_of_a_news_row_is_title_and_description():
    assert document_text({"titulo": "Sube el agua", "descripcion": "Lluvias en Chiriquí"}) == "Sube el agua. Lluvias en Chiriquí"


def test_the_text_of_a_row_without_description_is_the_title():
    assert document_text({"titulo": "Sube el agua", "descripcion": ""}) == "Sube el agua"
    assert document_text({"titulo": "Sube el agua"}) == "Sube el agua"


def test_the_model_directory_can_be_overridden_by_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("WHOAMI_EMBEDDING_MODEL_DIR", str(tmp_path / "m"))
    assert model_dir() == tmp_path / "m"

    monkeypatch.delenv("WHOAMI_EMBEDDING_MODEL_DIR")
    assert model_dir().name == "embeddinggemma-300m-q4"


def test_fetch_downloads_the_pinned_files_and_lays_them_out(tmp_path):
    requested = []

    def download(repo_id, filename, *, revision, cache_dir):
        requested.append((repo_id, filename, revision))
        source = tmp_path / "hub" / filename.replace("/", "_")
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(filename, encoding="utf-8")
        return str(source)

    target = tmp_path / "model"
    fetch_model(target, download=download)

    assert sorted(f for _, f, _ in requested) == sorted(MODEL_FILES)
    assert {(r, v) for r, _, v in requested} == {(embeddings.MODEL_REPO, MODEL_REVISION)}
    assert (target / "tokenizer.json").read_text(encoding="utf-8") == "tokenizer.json"
    assert (target / "onnx" / "model.onnx").read_text(encoding="utf-8") == "onnx/model_q4.onnx"
    assert (target / "onnx" / "model_q4.onnx_data").read_text(encoding="utf-8") == "onnx/model_q4.onnx_data"


def test_fetch_skips_files_already_present(tmp_path):
    target = tmp_path / "model"
    (target / "onnx").mkdir(parents=True)
    for name in ("tokenizer.json", "onnx/model.onnx", "onnx/model_q4.onnx_data"):
        (target / name).write_text("kept", encoding="utf-8")

    fetch_model(target, download=lambda *a, **k: pytest.fail("downloaded a file that was already there"))

    assert (target / "onnx" / "model.onnx").read_text(encoding="utf-8") == "kept"


@pytest.mark.skipif(not model_dir().exists(), reason="the local embedding model is not downloaded")
def test_the_real_model_returns_unit_vectors_of_768_dimensions():
    vectors = Embedder().embed_documents(["Sube el nivel del agua en el Canal", "Lluvias en Chiriquí"])

    assert vectors.shape == (2, 768)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)


# ----------------------------------------------------------------------------------------------- corpus


class FakeEmbedder:
    def __init__(self):
        self.documents = []

    def embed_documents(self, texts):
        self.documents.extend(texts)
        rng = np.random.default_rng(3)
        vectors = rng.normal(size=(len(texts), DIMENSIONS)).astype(np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def fake_model_dir(tmp_path):
    directory = tmp_path / "model"
    (directory / "onnx").mkdir(parents=True)
    (directory / "tokenizer.json").write_bytes(b"tok")
    (directory / "onnx" / "model.onnx").write_bytes(b"graph")
    (directory / "onnx" / "model_q4.onnx_data").write_bytes(b"data")
    return directory


ROWS = [
    {"id_noticia": "N-1", "titulo": "Sube el agua", "descripcion": "Lluvias en Chiriquí"},
    {"id_noticia": "N-2", "titulo": "Estrenan una película", "descripcion": ""},
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_the_corpus_is_embedded_with_the_text_recipe_and_saved_as_float16(tmp_path):
    embedder = FakeEmbedder()

    path = embed_corpus(ROWS, embedder, tmp_path / "out", fake_model_dir(tmp_path))

    assert path == tmp_path / "out" / "embeddinggemma-300m-q4.npy"
    assert embedder.documents == ["Sube el agua. Lluvias en Chiriquí", "Estrenan una película"]
    saved = np.load(path)
    assert saved.dtype == np.float16
    assert saved.shape == (2, 768)


def test_the_manifest_records_how_the_vectors_were_made(tmp_path):
    path = embed_corpus(ROWS, FakeEmbedder(), tmp_path / "out", fake_model_dir(tmp_path))

    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["modelo"] == embeddings.MODEL_REPO
    assert manifest["revision"] == MODEL_REVISION
    assert manifest["archivos"] == {
        "onnx/model_q4.onnx": sha256(b"graph"),
        "onnx/model_q4.onnx_data": sha256(b"data"),
        "tokenizer.json": sha256(b"tok"),
    }
    assert manifest["nombre"] == "embeddinggemma-300m-q4"
    assert manifest["dimensiones"] == 768
    assert manifest["dtype"] == "float16"
    assert manifest["prefijo_documento"] == DOCUMENT_PREFIX
    assert manifest["prefijo_consulta"] == QUERY_PREFIX
    assert manifest["receta_texto"] == embeddings.TEXT_RECIPE
    assert manifest["sha256_vectores"] == sha256(path.read_bytes())
    assert manifest["ids"] == ["N-1", "N-2"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", manifest["fecha_UTC"])


def test_the_saved_vectors_load_back_through_the_pipeline(tmp_path):
    path = embed_corpus(ROWS, FakeEmbedder(), tmp_path / "out", fake_model_dir(tmp_path))

    assert load_vectors(path, ROWS).shape == (2, 768)


def test_vectors_that_changed_after_the_manifest_was_written_are_rejected(tmp_path):
    path = embed_corpus(ROWS, FakeEmbedder(), tmp_path / "out", fake_model_dir(tmp_path))
    np.save(path, np.zeros((2, 768), dtype=np.float16))

    with pytest.raises(PipelineInputError, match="sha256_vectores"):
        load_vectors(path, ROWS)


def test_the_default_vectors_are_the_model_file_even_next_to_other_arrays(tmp_path, monkeypatch):
    path = embed_corpus(ROWS, FakeEmbedder(), tmp_path / "out", fake_model_dir(tmp_path))
    np.save(path.parent / "otro.npy", np.zeros((2, 4)))
    monkeypatch.setattr(run, "EMBEDDINGS_DIR", path.parent)

    assert default_vectors_path() == path
