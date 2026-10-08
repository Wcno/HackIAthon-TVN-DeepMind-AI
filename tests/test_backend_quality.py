"""The quality screen verifies the snapshot rather than just counting hashes."""

import hashlib
import json

from whoami.backend.service import quality_report
from whoami.contracts import PROCESSED


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
