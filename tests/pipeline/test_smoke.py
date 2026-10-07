import json
import time

import numpy as np
import pytest

from whoami import store
from whoami.cli import main
from whoami.pipeline.evidence import load_news_rows
from whoami.pipeline.run import run


def test_the_real_processed_data_runs_end_to_end_quickly_and_loads_back(tmp_path):
    rows = load_news_rows()
    embeddings = tmp_path / "embeddings"
    embeddings.mkdir()
    np.save(embeddings / "fake.npy", np.random.default_rng(7).normal(size=(len(rows), 16)))
    (embeddings / "manifest.json").write_text(json.dumps({"ids": [r["id_noticia"] for r in rows]}), encoding="utf-8")
    started = time.perf_counter()

    output = run(embeddings / "fake.npy", tmp_path / "data", tmp_path / "outputs")

    assert time.perf_counter() - started < 30
    assert sum(g.n_noticias for g in output.grupos) == len(rows)
    assert store.load(tmp_path / "data", tmp_path / "outputs").grupos == output.grupos


def test_the_pipeline_command_fails_clearly_when_the_vectors_do_not_exist(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["pipeline", "--vectors", str(tmp_path / "missing.npy")])

    assert exit_info.value.code == 2
    assert "no existe" in capsys.readouterr().err


def test_the_embed_command_writes_vectors_and_manifest_for_the_whole_news_file(tmp_path, monkeypatch, capsys):
    from whoami import cli
    from whoami.embeddings import DIMENSIONS

    class Fake:
        def embed_documents(self, texts):
            return np.ones((len(texts), DIMENSIONS), dtype=np.float32)

    model = tmp_path / "model"
    (model / "onnx").mkdir(parents=True)
    for name in ("tokenizer.json", "onnx/model.onnx", "onnx/model_q4.onnx_data"):
        (model / name).write_bytes(b"x")
    monkeypatch.setenv("WHOAMI_EMBEDDING_MODEL_DIR", str(model))
    monkeypatch.setattr(cli, "Embedder", Fake)
    monkeypatch.setattr(cli.pipeline, "EMBEDDINGS_DIR", tmp_path / "embeddings")

    assert cli.main(["embed"]) == 0

    rows = load_news_rows()
    manifest = json.loads((tmp_path / "embeddings" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ids"] == [r["id_noticia"] for r in rows]
    assert np.load(tmp_path / "embeddings" / "embeddinggemma-300m-q4.npy").shape == (len(rows), DIMENSIONS)
    assert "embeddinggemma-300m-q4.npy" in capsys.readouterr().out
