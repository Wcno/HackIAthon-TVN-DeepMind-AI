"""The quality screen verifies the snapshot rather than just counting hashes."""

import hashlib
import json

from whoami.backend.service import quality_report
from whoami.contracts import PROCESSED


def test_a_source_without_news_reports_every_day_of_the_window_without_news(tmp_path):
    from whoami.backend.reports import quality_view
    processed = tmp_path / "processed"
    processed.mkdir()
    news = {"ventana": {"desde": "2026-10-01T03:00:00Z", "hasta": "2026-10-04T03:00:00Z"}, "registros_leidos": 5,
            "noticias_unicas": 5, "incluidas": 0, "excluidas_por_motivo": {"fuera_de_ventana": 5}, "incluidas_por_origen_fecha": {},
            "cobertura_por_fuente": {"missing": {"incluidas": 0, "dias_con_noticias": 0, "dias_sin_noticias": "todos"}}}
    (processed / "calidad_noticias.json").write_text(json.dumps(news), encoding="utf-8")
    sources = [{"id_fuente": "missing", "medio": "Sin datos", "dominio": "example.test", "tipo": "medio",
                "canales": [{"canal": "rss", "url": "https://example.test/rss"}], "licencia": "n/a", "condiciones_reutilizacion": "n/a"}]
    (processed / "fuentes.json").write_text(json.dumps({"fuentes": sources}), encoding="utf-8")
    source = quality_view(processed)["news"]["coverage"]["groups"][0]["sources"][0]
    assert source["range"] == "Todos los días de la ventana sin noticias"
    assert "5 días" not in source["range"]


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
