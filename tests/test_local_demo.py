"""Local hosting refuses semantic degradation and keeps its own durable database."""

from fastapi.testclient import TestClient
import pytest

from whoami.backend.retrieval import CorpusRetriever
from whoami.backend.settings import Settings
from whoami.local_demo import create_demo


def test_requires_existing_online_configuration(tmp_path):
    with pytest.raises(ValueError, match="existing Gemini"):
        create_demo(Settings(), tmp_path / "demo.sqlite3")


def test_refuses_bm25_degradation_without_serving_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(CorpusRetriever, "search", lambda *args: [])
    settings = Settings(demo=False, offline=False, gemini_api_key="fixture-only")
    with pytest.raises(RuntimeError, match="degraded retrieval"):
        with TestClient(create_demo(settings, tmp_path / "demo.sqlite3")):
            pass


def test_readiness_keeps_secrets_private_and_persistent_database(tmp_path, monkeypatch):
    def search(index, *args):
        index.mode = "hybrid: fixture local embeddings + BM25"
        return []
    monkeypatch.setattr(CorpusRetriever, "search", search)
    database = tmp_path / "separate.sqlite3"
    settings = Settings(demo=False, offline=False, gemini_api_key="fixture-only", generation_daily_limit=10)
    for _ in range(2):
        with TestClient(create_demo(settings, database)) as client:
            readiness = client.get("/demo-readiness")
            assert readiness.json()["generation_daily_limit"] == 10
            assert readiness.json()["ready"] is True
            assert "fixture-only" not in readiness.text
            assert str(database) not in readiness.text
            assert client.get("/").status_code == 200
    assert database.is_file()
