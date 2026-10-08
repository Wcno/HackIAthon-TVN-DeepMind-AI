"""G10 acceptance at the public preparation CLI and HTTP boundaries."""

import json

import pytest

from whoami.cli import main
from whoami.offline import prepare, verify


def test_preparation_freezes_the_real_snapshot_without_secrets(tmp_path, capsys):
    destination = tmp_path / "demo"
    assert main(["offline-demo", "prepare", "--output", str(destination)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["cases"] >= 5
    assert report["answers"] == 48
    assert {"respondida", "abstencion"} <= set(report["query_states"])
    assert (destination / "data/processed/embeddings/manifest.json").is_file()
    assert (destination / "static/fonts/barlow-400-normal.woff2").is_file()
    assert not list(destination.rglob(".env"))
    assert not list(destination.rglob("*.onnx"))
    assert not list(destination.rglob("*.sqlite3"))
    assert main(["offline-demo", "verify", "--bundle", str(destination)]) == 0
    from whoami.evaluation.datasets import BENCHMARK
    from whoami.store import read_jsonl
    queries = read_jsonl(destination / "outputs/consultas.jsonl")
    assert {row["id"] for row in read_jsonl(BENCHMARK)} <= {row["id_consulta"] for row in queries}
    assert len({row["id_consulta"] for row in queries}) == len(queries)
    # An existing package is never silently replaced, including its saved human work.
    with pytest.raises(SystemExit):
        main(["offline-demo", "prepare", "--output", str(destination)])


@pytest.fixture
def bundle(tmp_path):
    path = tmp_path / "demo"
    prepare(path)
    return path


@pytest.mark.parametrize("name", ["outputs/consultas.jsonl", "static/htmx.min.js",
                                 "data/processed/embeddings/embeddinggemma-300m-q4.npy"])
def test_changed_or_missing_delivery_files_are_rejected(bundle, name):
    path = bundle / name
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Missing or changed offline file"):
        verify(bundle)
    path.unlink()
    with pytest.raises(ValueError, match="Missing or changed offline file"):
        verify(bundle)


def test_manifest_cannot_skip_required_files_or_escape_the_bundle(bundle):
    path = bundle / "offline.json"
    manifest = json.loads(path.read_text())
    manifest["sha256"]["../outside"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsafe offline path"):
        verify(bundle)
    manifest["sha256"].pop("../outside")
    manifest["sha256"].pop("outputs/consultas.jsonl")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="omits required"):
        verify(bundle)


def test_offline_app_ignores_online_settings_and_never_runs_a_model(bundle, monkeypatch, tmp_path):
    import httpx
    from fastapi.testclient import TestClient
    from whoami import embeddings, store
    from whoami.backend.app import create_app
    from whoami.offline import offline_settings

    def forbidden(*args, **kwargs):
        pytest.fail("Offline demo attempted local inference or provider HTTP")

    monkeypatch.setattr(embeddings, "Embedder", forbidden)
    monkeypatch.setenv("WHOAMI_OFFLINE", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "unused-test-key")
    settings = offline_settings(bundle, tmp_path / "db.sqlite3")
    assert settings.offline and not settings.gemini_api_key
    package = store.load(settings.data_directory, settings.output_directory)
    with TestClient(create_app(settings, gemini_transport=httpx.MockTransport(forbidden))) as client:
        for answer in package.consultas:
            response = client.get("/queries", params={"q": answer.consulta})
            assert response.status_code == 200
            assert f'data-estado="{answer.estado}"' in response.text
        unknown = client.get("/queries", params={"q": "Consulta no precalculada de G10"})
        assert "Sin conexión: solo" in unknown.text
        case = next(case for case in package.fichas if case.borrador)
        current = client.get(f"/api/cases/{case.id_caso}/draft").json()
        response = client.post(f"/api/cases/{case.id_caso}/assistant", json={
            "action": "articles", "question": "Busca otras noticias sobre este tema",
            "draft": current["draft"], "source_ids": current["source_ids"],
        })
        assert response.status_code == 200
        assert client.get("/static/app.css").status_code == 200
