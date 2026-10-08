"""`manifest.refresh` re-hashes only the files `whoami generar` rewrites, keeping the rest of the manifest as built."""

import json
from datetime import datetime

from whoami.ingest import manifest

CUTOFF = "2026-10-08T12:00:00Z"


def snapshot(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    groups, other = processed / "grupos.jsonl", processed / "otro.csv"
    groups.write_text("a\n", encoding="utf-8")
    other.write_text("x\n", encoding="utf-8")
    hashes = {"processed/grupos.jsonl": manifest._sha256(groups), "processed/otro.csv": manifest._sha256(other)}
    built = {"version": manifest._version(datetime.fromisoformat(CUTOFF), hashes), "fecha_corte_UTC": CUTOFF,
             "sha256": hashes, "licencias": {"k": "v"}}
    for path in (tmp_path / "manifest.json", processed / "manifest.json"):
        path.write_text(json.dumps(built), encoding="utf-8")
    return groups, built


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_refreshing_unchanged_files_leaves_both_manifests_as_they_were(tmp_path):
    groups, built = snapshot(tmp_path)
    manifest.refresh([groups], tmp_path)
    assert read(tmp_path / "manifest.json") == built == read(tmp_path / "processed" / "manifest.json")


def test_a_rewritten_file_gets_a_new_hash_and_version_in_both_manifests_and_nothing_else_changes(tmp_path):
    groups, built = snapshot(tmp_path)
    groups.write_text("b\n", encoding="utf-8")
    manifest.refresh([groups], tmp_path)
    refreshed = read(tmp_path / "manifest.json")
    assert refreshed == read(tmp_path / "processed" / "manifest.json")
    assert refreshed["sha256"]["processed/grupos.jsonl"] == manifest._sha256(groups)
    assert refreshed["sha256"]["processed/otro.csv"] == built["sha256"]["processed/otro.csv"]
    assert refreshed["version"] != built["version"] and refreshed["version"].startswith("20261008-")
    assert refreshed["licencias"] == built["licencias"] and refreshed["fecha_corte_UTC"] == CUTOFF


def test_the_generar_command_refreshes_the_manifest_of_the_files_it_rewrites(monkeypatch):
    from whoami.contracts import EVIDENCE_FILE, GROUPS_FILE, PROCESSED
    from whoami.generation import run

    refreshed = []
    monkeypatch.setattr(run, "generar", lambda *args: type("Summary", (), {"render": lambda self: ""})())
    monkeypatch.setattr(run, "default_llm", lambda: None)
    monkeypatch.setattr(run, "LocalEmbedder", lambda: None)
    monkeypatch.setattr(run.manifest, "refresh", refreshed.append)
    run.main(type("Args", (), {"modelo": "m", "top": 1, "consultas": None, "implicacion": False})())
    assert refreshed == [[PROCESSED / GROUPS_FILE, PROCESSED / EVIDENCE_FILE]]


def test_transformation_steps_are_readable_spanish_without_field_jargon():
    from whoami.ingest.manifest import TRANSFORMATIONS

    jargon = ("seendate", "lastmod", "§", "->", "fecha_deteccion", "fecha_publicacion")
    assert [step for step in TRANSFORMATIONS if any(word in step for word in jargon)] == []
