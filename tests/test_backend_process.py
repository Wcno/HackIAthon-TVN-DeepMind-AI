"""Acceptance over real HTTP and a real process restart, using isolated SQLite."""

import json
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from whoami.backend.pipeline import load_pipeline
from whoami.backend.settings import Settings
from whoami.store import load


@contextmanager
def running_server(database: Path, port: int, log: Path):
    environment = os.environ | {"WHOAMI_DATABASE": str(database), "WHOAMI_DEMO": "1", "WHOAMI_OFFLINE": "1"}
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "whoami.backend.app:app", "--host", "127.0.0.1",
             "--port", str(port), "--workers", "1"],
            env=environment, stdout=output, stderr=output,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 15
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError(f"Server exited during startup; see {log}")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(0.05)
                else:
                    raise AssertionError(f"Server startup timed out; see {log}")
                yield client, process.pid
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def test_all_screens_and_saved_decisions_survive_real_process_restart(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    settings = Settings(database=tmp_path / "runtime.sqlite3")
    bundle = load_pipeline(settings.data_directory, settings.output_directory)
    paths = ["/quality", "/inbox", "/queries"]
    paths += [path for group in bundle.groups for path in (f"/groups/{group['id_grupo']}", f"/groups/{group['id_grupo']}/context")]
    paths += [path for case in bundle.cases for path in (f"/cases/{case['id_caso']}", f"/cases/{case['id_caso']}/draft", f"/cases/{case['id_caso']}/review")]
    paths += [f"/evidence/{item['id_evidencia']}" for item in bundle.evidence]
    checked = []
    with running_server(settings.database, port, tmp_path / "first-server.log") as (client, first_pid):
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            assert "text/html" in response.headers["content-type"]
            assert "Demostración" in response.text
            if path == "/quality":
                assert "Integridad: verified" in response.text
            checked.append({"path": path, "status": response.status_code})
        for answer in bundle.answers:
            response = client.get("/queries", params={"q": answer["consulta"]})
            assert response.status_code == 200
            assert answer["estado"] in response.text
        assert client.get("/queries", params={"q": "Unseen offline query"}).status_code == 503
        decisions = ["requiere_evidencia", "en_revision", "aprobado_como_borrador", "descartado", "en_revision", "aprobado_como_borrador"]
        original_version = None
        for state in decisions:
            page = client.get("/cases/CASO-001/review")
            version = int(re.search(r'name="expected_version" value="(\d+)"', page.text).group(1))
            original_version = version if original_version is None else original_version
            response = client.post("/cases/CASO-001/review", data={
                "state": state, "actor": "Runtime reviewer", "note": "Real HTTP validation", "expected_version": version,
            })
            assert response.status_code == 200
            assert f"<strong>{state}</strong>" in response.text
        assert client.post("/cases/CASO-001/review", data={
            "state": "descartado", "actor": "Stale reviewer", "expected_version": original_version,
        }).status_code == 409
    with running_server(settings.database, port, tmp_path / "second-server.log") as (client, second_pid):
        assert second_pid != first_pid
        page = client.get("/cases/CASO-001/review")
        assert "<strong>aprobado_como_borrador</strong>" in page.text
        assert "Runtime reviewer" in page.text
        assert "Real HTTP validation" in page.text
        assert "aprobado_como_borrador" in client.get("/inbox").text
    destination = Path(os.environ.get("WHOAMI_VALIDATION_DELIVERY", tmp_path / "delivery"))
    exported_process = subprocess.run([
        sys.executable, "-m", "whoami.cli", "export-backend", "--database", str(settings.database),
        "--output", str(destination),
    ], capture_output=True, text=True, check=True)
    counts = json.loads(exported_process.stdout)
    exported = load(settings.data_directory, destination)
    assert exported.review_state("CASO-001") == "aprobado_como_borrador"
    report = os.environ.get("WHOAMI_VALIDATION_REPORT")
    if report:
        path = Path(report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "timestamp_utc": datetime.now(UTC).isoformat(), "synthetic": True,
            "real_http_views": checked, "query_outcomes": [answer["estado"] for answer in bundle.answers],
            "saved_transitions": decisions, "different_processes": first_pid != second_pid,
            "state_after_restart": exported.review_state("CASO-001"), "g2_export": counts,
            "snapshot_integrity": "verified",
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
