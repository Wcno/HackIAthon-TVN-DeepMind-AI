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
        main(["pipeline", "--sin-llm", "--vectors", str(tmp_path / "missing.npy")])

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


class AnsweringLLM:
    """Answers every topic call with `turismo` and every pair with `different`; every other call is a cache hit."""

    def __init__(self):
        self.calls = 0

    def complete(self, model, messages, *, purpose, **options):
        self.calls += 1
        answer = {"tema": "turismo", "confianza": 0.7} if purpose == "g3-tema-llm" else {"mismo_hecho": False}
        cached = self.calls % 2 == 0
        return type("Completion", (), {"cached": cached, "json": lambda self: answer})()


def run_cli(tmp_path, monkeypatch, *args):
    from whoami import cli

    rows = load_news_rows()
    embeddings = tmp_path / "embeddings"
    embeddings.mkdir()
    np.save(embeddings / "fake.npy", np.random.default_rng(7).normal(size=(len(rows), 16)))
    (embeddings / "manifest.json").write_text(json.dumps({"ids": [r["id_noticia"] for r in rows]}), encoding="utf-8")
    real_run = cli.pipeline.run
    monkeypatch.setattr(
        cli.pipeline, "run", lambda vectors, configure: real_run(vectors, tmp_path / "data", tmp_path / "outputs", configure=configure)
    )
    return cli.main(["pipeline", "--vectors", str(embeddings / "fake.npy"), *args])


def test_the_offline_pipeline_command_never_creates_an_llm_and_prints_the_summary(tmp_path, monkeypatch, capsys):
    from whoami import cli

    monkeypatch.setattr(cli, "default_llm", lambda: (_ for _ in ()).throw(AssertionError("an LLM was created")))

    assert run_cli(tmp_path, monkeypatch, "--sin-llm") == 0

    out = capsys.readouterr().out
    assert "grupos" in out
    assert "temas" in out
    assert "contexto" in out
    assert "llamadas LLM: ninguna" in out


def test_the_pipeline_command_with_an_llm_reports_its_calls(tmp_path, monkeypatch, capsys):
    from whoami import cli

    llm = AnsweringLLM()
    monkeypatch.setattr(cli, "default_llm", lambda: llm)

    assert run_cli(tmp_path, monkeypatch) == 0

    out = capsys.readouterr().out
    assert "g3-tema-llm" in out
    assert llm.calls > 0
    assert "en caché" in out and "a la red" in out


def test_the_llm_model_option_reaches_the_calls(tmp_path, monkeypatch):
    from whoami import cli

    seen = set()

    class Spy(AnsweringLLM):
        def complete(self, model, messages, **options):
            seen.add(model)
            return super().complete(model, messages, **options)

    monkeypatch.setattr(cli, "default_llm", lambda: Spy())

    run_cli(tmp_path, monkeypatch, "--modelo-llm", "gemini-3.1-flash-lite")

    assert seen == {"gemini-3.1-flash-lite"}


def test_a_missing_api_key_is_a_clear_error_that_suggests_the_offline_mode(tmp_path, monkeypatch, capsys):
    from whoami import cli

    def no_key():
        raise KeyError("GEMINI_API_KEY")

    monkeypatch.setattr(cli, "default_llm", no_key)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["pipeline", "--vectors", str(tmp_path / "missing.npy")])

    assert exit_info.value.code == 2
    assert "--sin-llm" in capsys.readouterr().err
