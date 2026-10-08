"""Prove live human decisions remain loadable by the final G2 file contract."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from whoami.backend.export import export_backend
from whoami.backend.pipeline import load_pipeline
from whoami.backend.repository import EditorialRepository, ReviewConflict
from whoami.backend.settings import Settings
from whoami.store import load


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
