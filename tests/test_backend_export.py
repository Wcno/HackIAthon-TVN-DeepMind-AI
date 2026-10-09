"""Prove live human decisions remain loadable by the final G2 file contract."""

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from whoami.backend.export import export_backend
from whoami.backend.pipeline import load_pipeline
from whoami.backend.repository import EditorialRepository, ReviewConflict
from whoami.backend.settings import Settings
from whoami.contracts import DEMO, FICHAS_FILE, GROUPS_FILE, REVIEWS_FILE
from whoami.store import load, read_jsonl, write_jsonl


def test_export_round_trip_keeps_live_decision_and_seed_inputs(tmp_path):
    settings = Settings(database=tmp_path / "editorial.sqlite3")
    repository = EditorialRepository(settings.database)
    bundle = load_pipeline(settings.data_directory, settings.output_directory)
    seed_bytes = (settings.output_directory / "revisiones.jsonl").read_bytes()
    repository.import_bundle(bundle)
    case = repository.case("CASO-001")
    repository.review("CASO-001", state="descartado", actor="Export reviewer", note="Checked the draft",
                      expected_version=case["version"])
    destination = tmp_path / "delivery"
    counts = export_backend(repository, destination)
    output = load(settings.data_directory, destination)
    assert output.review_state("CASO-001") == "descartado"
    assert len(output.fichas) == len(bundle.cases) == counts["fichas.jsonl"]
    assert any(review.responsable == "Export reviewer" for review in output.revisiones)
    assert (settings.output_directory / "revisiones.jsonl").read_bytes() == seed_bytes
    first = {path.name: path.read_bytes() for path in destination.iterdir()}
    export_backend(repository, destination)
    assert {path.name: path.read_bytes() for path in destination.iterdir()} == first


def test_changed_content_exports_only_its_current_review_cycle(tmp_path):
    settings = Settings(database=tmp_path / "editorial.sqlite3")
    repository = EditorialRepository(settings.database)
    bundle = load_pipeline(settings.data_directory, settings.output_directory)
    repository.import_bundle(bundle)
    previous_history = repository.review_history("CASO-005")
    changed = tuple(case | {"accion_recomendada": "Review the updated content"} if case["id_caso"] == "CASO-005" else case
                    for case in bundle.cases)
    repository.import_bundle(replace(bundle, cases=changed))
    destination = tmp_path / "delivery"
    export_backend(repository, destination)
    output = load(settings.data_directory, destination)
    assert output.review_state("CASO-005") == "nuevo"
    assert not any(review.id_caso == "CASO-005" for review in output.revisiones)
    assert any(review["estado"] == "aprobado_como_borrador" for review in repository.review_history("CASO-005"))
    assert len(repository.review_history("CASO-005")) == len(previous_history)
    fresh = EditorialRepository(tmp_path / "fresh.sqlite3")
    fresh.import_bundle(load_pipeline(settings.data_directory, destination))
    assert fresh.case("CASO-005")["estado_revision"] == "nuevo"
    assert any(review["estado"] == "aprobado_como_borrador" for review in fresh.review_history("CASO-005"))


def test_two_concurrent_reviewers_cannot_overwrite_each_other(tmp_path):
    settings = Settings(database=tmp_path / "editorial.sqlite3")
    repository = EditorialRepository(settings.database)
    repository.import_bundle(load_pipeline(settings.data_directory, settings.output_directory))
    version = repository.case("CASO-001")["version"]
    barrier = Barrier(2)

    def decide(actor):
        barrier.wait(timeout=5)
        try:
            return repository.review("CASO-001", state="descartado", actor=actor, note="Concurrent decision",
                                     expected_version=version)
        except ReviewConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ("First reviewer", "Second reviewer")))
    assert results.count("conflict") == 1
    assert repository.case("CASO-001")["version"] == version + 1
    assert len([review for review in repository.review_history("CASO-001") if review["nota"] == "Concurrent decision"]) == 1


def test_a_reviewed_case_whose_pipeline_content_changes_shows_each_event_once(tmp_path):
    from dataclasses import replace
    from whoami.backend.pipeline import load_pipeline
    from whoami.backend.presentation import review_timeline
    from whoami.contracts import DEMO
    bundle = load_pipeline(DEMO, DEMO)
    repository = EditorialRepository(tmp_path / "db.sqlite3")
    repository.import_bundle(bundle)
    case_id = "CASO-004"
    version = repository.case(case_id)["version"]
    repository.review(case_id, state="en_revision", actor="Ana", note=None, expected_version=version)
    changed = replace(bundle, cases=tuple(
        case | {"afirmaciones": [claim | {"texto": claim["texto"] + " (actualizado)"} for claim in case["afirmaciones"]]}
        if case["id_caso"] == case_id else case for case in bundle.cases))
    repository.import_bundle(changed)
    exported = repository.snapshot_export()[0]
    repository.import_bundle(exported)  # a round trip through the delivery files must not repeat anything

    history, audit = repository.review_history(case_id), repository.audit_history(case_id)
    by_decision = [(item["estado"], item["responsable"], item["fecha"]) for item in history]
    assert len(by_decision) == len(set(by_decision))
    assert sum(item["estado"] == "en_revision" and item["responsable"] == "Ana" for item in history) == 1
    timeline = review_timeline(history, audit)
    edits = [item for item in timeline if item["kind"] == "edit"]
    assert len(edits) == len({(item["title"], item["content_version"]) for item in edits}) == len(audit)


def test_a_case_file_generated_live_is_exported_as_a_loadable_package(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(DEMO, data)
    generated = next(record for record in read_jsonl(data / FICHAS_FILE) if record["id_caso"] == "CASO-005")
    write_jsonl(data / GROUPS_FILE, [group | {"id_caso": None} if group["id_grupo"] == generated["id_grupo"] else group
                                     for group in read_jsonl(data / GROUPS_FILE)])
    for name in (FICHAS_FILE, REVIEWS_FILE):
        write_jsonl(data / name, [row for row in read_jsonl(data / name) if row["id_caso"] != "CASO-005"])
    repository = EditorialRepository(tmp_path / "editorial.sqlite3")
    repository.import_bundle(load_pipeline(data, data))
    bundle = load_pipeline(DEMO, DEMO)
    repository.add_generated_case(next(case for case in bundle.cases if case["id_caso"] == "CASO-005"))
    destination = tmp_path / "delivery"
    export_backend(repository, destination)
    output = load(data, destination)
    assert next(group for group in output.grupos if group.id_grupo == generated["id_grupo"]).id_caso == "CASO-005"
    assert any(case.id_caso == "CASO-005" for case in output.fichas)
