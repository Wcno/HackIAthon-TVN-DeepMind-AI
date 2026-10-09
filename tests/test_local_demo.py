"""Local hosting refuses semantic degradation and keeps its own durable database."""

import argparse

from fastapi.testclient import TestClient
import pytest
import uvicorn

from whoami import local_demo
from whoami.backend.retrieval import CorpusRetriever
from whoami.backend.settings import Settings
from whoami.local_demo import create_demo


@pytest.mark.parametrize("arguments, host", [([], "127.0.0.1"), (["--host", "0.0.0.0"], "0.0.0.0")])
def test_serves_on_loopback_unless_a_container_asks_for_every_interface(tmp_path, monkeypatch, arguments, host):
    served = {}
    monkeypatch.setattr(local_demo, "create_demo", lambda settings, database: "app")
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: served.update(options))
    parser = argparse.ArgumentParser()
    local_demo.add_arguments(parser)
    local_demo.main(parser.parse_args(["--database", str(tmp_path / "demo.sqlite3"), *arguments]))
    assert served == {"host": host, "port": 8765}


def test_requires_existing_online_configuration(tmp_path):
    with pytest.raises(ValueError, match="existing Gemini"):
        create_demo(Settings(), tmp_path / "demo.sqlite3")


def test_refuses_bm25_degradation_without_serving_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(CorpusRetriever, "search", lambda *args: [])
    settings = Settings(demo=False, offline=False, gemini_api_key="fixture-only")
    with pytest.raises(RuntimeError, match="degraded retrieval"):
        with TestClient(create_demo(settings, tmp_path / "demo.sqlite3")):
            pass


@pytest.mark.parametrize("daily_limit", [None, 10, 100])
def test_readiness_keeps_secrets_private_and_persistent_database(tmp_path, monkeypatch, daily_limit):
    def search(index, *args):
        index.mode = "hybrid: fixture local embeddings + BM25"
        return []
    monkeypatch.setattr(CorpusRetriever, "search", search)
    database = tmp_path / "separate.sqlite3"
    settings = Settings(demo=False, offline=False, gemini_api_key="fixture-only", generation_daily_limit=daily_limit)
    for _ in range(2):
        with TestClient(create_demo(settings, database)) as client:
            readiness = client.get("/demo-readiness")
            assert readiness.json()["generation_daily_limit"] == daily_limit
            assert readiness.json()["ready"] is True
            assert "fixture-only" not in readiness.text
            assert str(database) not in readiness.text
            assert client.get("/").status_code == 200
    assert database.is_file()
