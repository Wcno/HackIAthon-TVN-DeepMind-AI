"""G5 acceptance: all screens, restart persistence and concurrent human decisions."""

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.pipeline import PipelineBundle, load_pipeline
from whoami.backend.repository import EditorialRepository, InvalidReview, MissingRecord
from whoami.backend.settings import Settings
from whoami.schemas import ReviewRecord, current_review_state, transition_errors


@pytest.fixture
def settings(tmp_path):
    return Settings(database=tmp_path / "editorial.sqlite3")


def test_every_contract_screen_and_htmx_fragment(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["status"] == "ready"
        for path in ("/quality", "/inbox", "/groups/G-001", "/groups/G-001/context",
                     "/cases/CASO-001", "/cases/CASO-001/draft", "/cases/CASO-001/review", "/queries"):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
            assert "text/html" in response.headers["content-type"]
            assert "Demostración" in response.text
        assert "<html" not in client.get("/inbox", headers={"HX-Request": "true"}).text
        assert client.get("/groups/missing").status_code == 404
        assert client.get("/cases/missing").status_code == 404
        assert client.get("/evidence/missing").status_code == 404


def test_human_decision_survives_restart_and_keeps_seed_files_untouched(settings):
    seed = (settings.output_directory / "fichas.jsonl").read_bytes()
    with TestClient(create_app(settings)) as client:
        repository = client.app.state.repository
        case = repository.case("CASO-001")
        state = "descartado" if case["estado_revision"] != "descartado" else "en_revision"
        response = client.post("/cases/CASO-001/review", data={
            "state": state, "actor": "Editorial reviewer", "expected_version": case["version"], "note": "Checked evidence",
        }, headers={"HX-Request": "true"})
        assert response.status_code == 200, response.text
        assert "Editorial reviewer" in response.text
        stale = client.post("/cases/CASO-001/review", data={
            "state": "en_revision", "actor": "Second reviewer", "expected_version": case["version"],
        })
        assert stale.status_code == 409
    with TestClient(create_app(settings)) as client:
        case = client.app.state.repository.case("CASO-001")
        assert case["estado_revision"] == state
        assert case["version"] == 2
        assert "Editorial reviewer" in client.get("/cases/CASO-001/review").text
        assert state in client.get("/inbox").text
        records = [ReviewRecord.model_validate(record) for record in client.app.state.repository.current_review_records("CASO-001")]
        assert transition_errors(records) == []
        assert current_review_state(records, "CASO-001") == state
    assert (settings.output_directory / "fichas.jsonl").read_bytes() == seed


def test_invalid_transitions_and_insufficient_evidence_are_blocked(settings):
    with TestClient(create_app(settings)) as client:
        repository = client.app.state.repository
        for group in repository.records("group"):
            if not group.get("id_caso"):
                continue
            case = repository.case(group["id_caso"])
            if case["estado_evidencia"] != "insuficiente":
                continue
            if case["estado_revision"] != "en_revision":
                repository.review(case["id_caso"], state="en_revision", actor="Reviewer", note="Check gaps", expected_version=case["version"])
                case = repository.case(case["id_caso"])
            with pytest.raises(InvalidReview, match="Approval requires"):
                repository.review(case["id_caso"], state="aprobado_como_borrador", actor="Reviewer", note=None,
                                  expected_version=case["version"])
            assert repository.case(case["id_caso"])["version"] == case["version"]
            break
        else:
            pytest.fail("The demo must contain an insufficient-evidence case.")
        case = repository.case("CASO-001")
        with pytest.raises(InvalidReview):
            repository.review(case["id_caso"], state=case["estado_revision"], actor="Reviewer", note=None,
                              expected_version=case["version"])
        assert client.post("/cases/CASO-001/review", data={"state": "en_revision", "actor": " ", "expected_version": 1}).status_code == 422


def test_pipeline_changes_revoke_approval_and_preserve_history(settings):
    bundle = load_pipeline(settings.data_directory, settings.output_directory)
    repository = EditorialRepository(settings.database)
    repository.import_bundle(bundle)
    case = repository.case("CASO-001")
    if case["estado_revision"] != "en_revision":
        repository.review("CASO-001", state="en_revision", actor="Reviewer", note="Review evidence", expected_version=case["version"])
    case = repository.case("CASO-001")
    repository.review("CASO-001", state="aprobado_como_borrador", actor="Reviewer", note="Verified", expected_version=case["version"])
    approved = repository.case("CASO-001")
    changed_cases = tuple(dict(item, accion_recomendada="Changed recommendation") if item["id_caso"] == "CASO-001" else item for item in bundle.cases)
    repository.import_bundle(replace(bundle, cases=changed_cases))
    assert repository.case("CASO-001")["estado_revision"] == "nuevo"
    assert repository.case("CASO-001")["version"] == approved["version"] + 1
    assert any(review["estado"] == "aprobado_como_borrador" for review in repository.review_history("CASO-001"))
    assert repository.current_review_records("CASO-001") == []
    changed = repository.case("CASO-001")
    repository.review("CASO-001", state="en_revision", actor="Reviewer", note="Check the new content", expected_version=changed["version"])
    records = [ReviewRecord.model_validate(record) for record in repository.current_review_records("CASO-001")]
    assert transition_errors(records) == []
    assert all(record.responsable == "Reviewer" for record in records)
    assert repository.audit_history("CASO-001")


def test_precomputed_queries_abstention_and_safe_html(settings):
    with TestClient(create_app(settings)) as client:
        answers = client.app.state.repository.records("answer")
        for answer in answers:
            response = client.get("/queries", params={"q": answer["consulta"]})
            assert response.status_code == 200
            assert answer["estado"] in response.text
        response = client.get("/queries", params={"q": "An unavailable query"})
        assert response.status_code == 503
        assert "solo consultas precalculadas" in response.text
        repository = client.app.state.repository
        with repository.connection() as connection:
            record = repository.record("group", "G-001")
            record["titulo"] = "<script>alert('source')</script>"
            connection.execute("UPDATE records SET body = ? WHERE kind = 'group' AND id = 'G-001'", (json.dumps(record),))
        page = client.get("/groups/G-001").text
        assert "<script>alert" not in page
        assert "&lt;script&gt;" in page


def test_g4_provider_seam_validates_citations_and_never_runs_offline(settings):
    calls = []

    async def provider(query, gemini, repository):
        calls.append(query)
        return repository.records("answer")[0] | {"consulta": query}

    with TestClient(create_app(settings, query_provider=provider)) as client:
        assert client.get("/queries", params={"q": "New query"}).status_code == 503
        assert calls == []
    with TestClient(create_app(replace(settings, offline=False), query_provider=provider)) as client:
        assert client.get("/queries", params={"q": "New query"}).status_code == 200
        assert calls == ["New query"]

    async def broken_provider(query, gemini, repository):
        return {"id_consulta": "Q-test", "consulta": query, "estado": "respondida", "respuesta": "Unsupported",
                "citas": [{"id_evidencia": "N-missing", "campo": "titulo", "pasaje": "Unsupported"}]}

    with TestClient(create_app(replace(settings, offline=False), query_provider=broken_provider)) as client:
        assert client.get("/queries", params={"q": "New query"}).status_code == 503


def test_removed_cases_are_archived_and_cannot_remain_approved(settings):
    bundle = load_pipeline(settings.data_directory, settings.output_directory)
    repository = EditorialRepository(settings.database)
    repository.import_bundle(bundle)
    original_history = len(repository.review_history("CASO-005"))
    repository.import_bundle(PipelineBundle((), (), (), (), ()))
    with pytest.raises(MissingRecord):
        repository.case("CASO-005")
    with pytest.raises(MissingRecord):
        repository.review("CASO-005", state="en_revision", actor="Reviewer", note="Reopen", expected_version=2)
    with repository.connection() as connection:
        assert connection.execute("SELECT count(*) FROM reviews WHERE case_id = 'CASO-005'").fetchone()[0] == original_history
        assert repository._current_review(connection, "CASO-005") is None
    repository.import_bundle(bundle)
    assert repository.case("CASO-005")["estado_revision"] == "nuevo"
    assert repository.current_review_records("CASO-005") == []


def test_htmx_errors_and_draft_claims_preserve_screen_contract(settings):
    with TestClient(create_app(settings)) as client:
        for path in ("/cases/missing", "/queries?q=new-query"):
            response = client.get(path, headers={"HX-Request": "true"})
            assert response.status_code in (404, 503)
            assert "text/html" in response.headers["content-type"]
            assert 'role="alert"' in response.text
            assert "<html" not in response.text
        response = client.post("/cases/CASO-001/review", data={
            "state": "en_revision", "actor": "Reviewer", "expected_version": 999,
        }, headers={"HX-Request": "true"})
        assert response.status_code == 409
        assert 'role="alert"' in response.text and "<html" not in response.text
        case = client.app.state.repository.case("CASO-001")
        draft = client.get("/cases/CASO-001/draft").text
        for claim in case["afirmaciones"]:
            assert claim["tipo"] in draft
            for citation in claim["citas"]:
                assert "/evidence/" + citation["id_evidencia"] in draft


def test_empty_optional_form_note_remains_valid_g2_history(settings):
    with TestClient(create_app(settings)) as client:
        repository = client.app.state.repository
        case = repository.case("CASO-001")
        response = client.post("/cases/CASO-001/review", data={
            "state": "descartado", "actor": "Reviewer", "expected_version": case["version"], "note": "   ",
        })
        assert response.status_code == 200
        records = [ReviewRecord.model_validate(record) for record in repository.current_review_records("CASO-001")]
        assert transition_errors(records) == []
        assert records[-1].nota is None
