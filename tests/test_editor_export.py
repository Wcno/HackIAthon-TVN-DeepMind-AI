"""Export saved human drafts separately from validated pipeline seeds."""

import json

from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.export import export_backend
from whoami.backend.repository import EditorialRepository
from whoami.backend.settings import Settings
from whoami.store import load


COMPANION = "borradores_editoriales.jsonl"


def test_export_preserves_flexible_draft_and_scopes_approval_to_it(tmp_path):
    settings = Settings(database=tmp_path / "editor.sqlite3")
    with TestClient(create_app(settings)) as client:
        record = client.get("/api/cases/CASO-004/draft").json()
        record["draft"]["titulo"] = "Título guardado por una persona"
        record["draft"]["preguntas"] = ["¿Qué falta verificar?"]
        saved = client.put("/api/cases/CASO-004/draft", json={
            "draft": record["draft"], "source_ids": record["source_ids"],
            "expected_version": record["version"],
        })
        assert saved.status_code == 200
        for state in ("en_revision", "aprobado_como_borrador"):
            version = client.get("/api/cases/CASO-004/draft").json()["version"]
            assert client.post("/cases/CASO-004/review", data={
                "state": state, "actor": "Human editor", "expected_version": version,
            }).status_code == 200
        current = client.get("/api/cases/CASO-004/draft").json()
    destination = tmp_path / "delivery"
    counts = export_backend(EditorialRepository(settings.database), destination)
    assert counts[COMPANION] == 1
    companion = json.loads((destination / COMPANION).read_text(encoding="utf-8"))
    assert companion["id_caso"] == "CASO-004"
    assert companion["draft"] == record["draft"]
    assert companion["source_ids"] == record["source_ids"]
    assert companion["version"] == current["version"]
    assert companion["review_state"] == "aprobado_como_borrador"
    assert companion["reviews"][-1]["responsable"] == "Human editor"
    assert all(review["content_version"] == companion["content_version"] for review in companion["reviews"])
    output = load(settings.data_directory, destination)
    assert output.review_state("CASO-004") == "nuevo"
    assert not any(review.id_caso == "CASO-004" for review in output.revisiones)
    seed = next(case for case in output.fichas if case.id_caso == "CASO-004")
    assert seed.borrador.titulo != record["draft"]["titulo"]


def test_export_without_overlays_keeps_existing_artifacts(tmp_path):
    settings = Settings(database=tmp_path / "editor.sqlite3")
    with TestClient(create_app(settings)):
        pass
    destination = tmp_path / "delivery"
    counts = export_backend(EditorialRepository(settings.database), destination)
    assert set(counts) == {"fichas.jsonl", "revisiones.jsonl", "consultas.jsonl"}
    assert not (destination / COMPANION).exists()
    load(settings.data_directory, destination)
