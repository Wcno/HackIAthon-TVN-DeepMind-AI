"""The quality screen verifies the snapshot rather than just counting hashes."""

import hashlib
import json

from whoami.backend.service import quality_report
from whoami.contracts import PROCESSED


def test_quality_screen_reports_all_missing_days_without_counting_a_string():
    from jinja2 import Environment, FileSystemLoader
    from whoami.backend.app import panama_time
    from pathlib import Path
    env = Environment(loader=FileSystemLoader(Path(__file__).parents[1] / "src/whoami/backend/templates"))
    env.filters["panama_time"] = panama_time
    reports = {name: {"available": False} for name in ["calidad_indicadores.json", "calidad_inec.json", "calidad_eventos.json", "manifest"]}
    reports["calidad_noticias.json"] = {"registros_leidos": 0, "incluidas": 0, "ventana": None,
        "excluidas_por_motivo": {}, "cobertura_por_fuente": {"missing": {"incluidas": 0, "dias_con_noticias": 0, "dias_sin_noticias": "todos"}}}
    html = env.get_template("quality.html").render(reports=reports)
    assert "5 días sin noticias" not in html
    assert "todos los días de la ventana sin noticias" in html


def test_snapshot_integrity_distinguishes_verified_missing_and_changed(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    source = processed / "noticias.csv"
    source.write_bytes(b"id,titulo\nN-1,Headline\n")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps({"sha256": {"processed/noticias.csv": expected}}), encoding="utf-8")
    assert quality_report(processed)["manifest"]["integrity"]["status"] == "verified"
    source.write_bytes(b"changed")
    integrity = quality_report(processed)["manifest"]["integrity"]
    assert integrity["status"] == "invalid"
    assert integrity["mismatches"] == ["processed/noticias.csv"]
    source.unlink()
    integrity = quality_report(processed)["manifest"]["integrity"]
    assert integrity["status"] == "incomplete"
    assert integrity["missing"] == ["processed/noticias.csv"]


def test_manifest_paths_cannot_read_outside_the_snapshot(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({"sha256": {"../outside.csv": "unused"}}), encoding="utf-8")
    integrity = quality_report(processed)["manifest"]["integrity"]
    assert integrity["status"] == "invalid"
    assert integrity["unsafe_paths"] == ["../outside.csv"]


def test_checked_in_processed_snapshot_matches_its_manifest():
    integrity = quality_report(PROCESSED)["manifest"]["integrity"]
    assert integrity["status"] == "verified", integrity
