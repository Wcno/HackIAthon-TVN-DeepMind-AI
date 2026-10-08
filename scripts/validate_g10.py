"""Rehearse the production snapshot with external networking and local models forbidden.

Run after installing dependencies and Chromium, before disconnecting the demo laptop.
Only the validation child is isolated; this never changes the host's Wi-Fi settings.
"""

import argparse
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
from urllib.parse import urlsplit

import httpx

from whoami import offline, store


def guarded_server(bundle: Path, port: int, audit: Path) -> None:
    """Deny external DNS/socket connections and any attempt to instantiate an embedder."""
    from whoami import embeddings
    from whoami.cli import main

    attempts = []
    audit.write_text("[]\n", encoding="utf-8")

    def deny(kind, target):
        attempts.append({"kind": kind, "target": str(target)})
        audit.write_text(json.dumps(attempts), encoding="utf-8")
        raise OSError(f"G10 isolation refused {kind}")

    allowed = {"127.0.0.1", "::1", "localhost"}
    connect, connect_ex, resolve = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def checked(method, connection, address):
        if connection.family in {socket.AF_INET, socket.AF_INET6} and address[0] not in allowed:
            deny("external_socket", address[0])
        return method(connection, address)

    def dns(host, *args, **kwargs):
        if host not in allowed and host not in {None, b"localhost", b"127.0.0.1", b"::1"}:
            deny("external_dns", host)
        return resolve(host, *args, **kwargs)

    socket.socket.connect = lambda connection, address: checked(connect, connection, address)
    socket.socket.connect_ex = lambda connection, address: checked(connect_ex, connection, address)
    socket.getaddrinfo = dns
    embeddings.Embedder = lambda *args, **kwargs: deny("local_model", "Embedder")
    main(["offline-demo", "serve", "--bundle", str(bundle), "--port", str(port)])


@contextmanager
def server(bundle: Path, log: Path, audit: Path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    # Deliberately hostile ambient configuration: serve must force offline even with an API key.
    environment = os.environ | {"WHOAMI_OFFLINE": "0", "WHOAMI_DEMO": "0", "GEMINI_API_KEY": "unused-g10-test-key",
                                "PYTHONUTF8": "1"}
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--server", "--bundle", str(bundle),
                                    "--port", str(port), "--audit", str(audit)], env=environment,
                                   stdout=output, stderr=output,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15, trust_env=False) as client:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError(f"Offline server exited: {log.read_text(encoding='utf-8')}")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("Offline server did not become ready")
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        assert json.loads(audit.read_text(encoding="utf-8")) == [], "Offline process attempted network or inference"


def browser_rehearsal(base: str, paths: list[str], answers, case_id: str, directory: Path) -> dict:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = playwright.chromium.launch(executable_path=executable, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block")
        external, errors, failed = [], [], []

        def route(request):
            if urlsplit(request.request.url).netloc == urlsplit(base).netloc:
                request.continue_()
            else:
                external.append(request.request.url)
                request.abort()

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: failed.append(response.url) if response.status >= 400 else None)
        page.on("requestfailed", lambda request: failed.append(request.url))
        try:
            for index, path in enumerate(paths):
                response = page.goto(base + path, wait_until="networkidle")
                assert response.status == 200, path
                page.screenshot(path=str(directory / f"stage-{index + 1}.png"), full_page=True)
            for state in ("respondida", "abstencion", "contradiccion"):
                answer = next((answer for answer in answers if answer.estado == state), None)
                if answer is None:
                    continue
                page.goto(base + "/queries")
                page.get_by_label("Pregunta sobre la agenda").fill(answer.consulta)
                page.get_by_role("button", name="Consultar", exact=True).click()
                expect(page.locator(f'[data-estado="{state}"]')).to_be_visible()
            page.get_by_label("Pregunta sobre la agenda").fill("Pregunta inédita de G10 fuera del precálculo")
            page.get_by_role("button", name="Consultar", exact=True).click()
            expect(page.get_by_text("No hay una respuesta precalculada para esta consulta", exact=True)).to_be_visible()
            page.goto(base + f"/cases/{case_id}/draft")
            page.get_by_role("tab", name="Historia", exact=True).click()
            expect(page.locator('[data-editor]')).to_have_count(0)
            page.get_by_role("tab", name="Borrador", exact=True).click()
            expect(page.locator('[data-editor]')).to_have_count(1)
            title = page.locator('textarea[data-key="titulo"]')
            title.fill("Titular editado durante el ensayo offline G10")
            page.get_by_role("button", name="Guardar cambios", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="Cambios guardados")).to_be_visible()
            page.reload()
            expect(title).to_have_value("Titular editado durante el ensayo offline G10")
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(base + "/inbox", wait_until="networkidle")
            page.screenshot(path=str(directory / "inbox-mobile.png"), full_page=True)
            assert not external and not errors and not failed, (external, errors, failed)
            return {"external_requests": external, "javascript_errors": errors, "failed_requests": failed,
                    "draft_saved_in_browser": True, "desktop_and_mobile": True}
        finally:
            browser.close()


def rehearse(destination: Path, *, browser: bool) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    bundle = destination / "bundle"
    counts = offline.prepare(bundle)
    package = store.load(bundle / "data/processed", bundle / "outputs")
    case = next(case for case in package.fichas if case.borrador)
    paths = ["/quality", "/inbox", f"/groups/{case.id_grupo}", f"/groups/{case.id_grupo}/context",
             f"/cases/{case.id_caso}", f"/cases/{case.id_caso}/draft", f"/cases/{case.id_caso}/review"]
    checked, queries, browser_report = [], [], None
    audit = destination / "isolation-first.json"
    with server(bundle, destination / "server-first.log", audit) as client:
        for path in paths + ["/methodology"]:
            response = client.get(path)
            assert response.status_code == 200, path
            checked.append({"path": path, "status": response.status_code})
        for answer in package.consultas:
            response = client.get("/queries", params={"q": answer.consulta})
            assert response.status_code == 200 and f'data-estado="{answer.estado}"' in response.text
            queries.append({"id": answer.id_consulta, "state": answer.estado})
        missing = client.get("/queries", params={"q": "Pregunta inédita de G10 fuera del precálculo"})
        assert missing.status_code == 200 and "Sin conexión: solo" in missing.text
        without_case = next(group for group in package.grupos if group.id_grupo not in {case.id_grupo for case in package.fichas})
        refusal = client.post(f"/groups/{without_case.id_grupo}/case-file")
        assert refusal.status_code == 409 and "necesita Gemini" in refusal.text
        if browser:
            browser_report = browser_rehearsal(str(client.base_url).rstrip("/"), paths, package.consultas, case.id_caso, destination)
        record = client.get(f"/api/cases/{case.id_caso}/draft").json()
        search = client.post(f"/api/cases/{case.id_caso}/assistant", json={"action": "articles",
                             "question": "Busca otras noticias sobre este tema", "draft": record["draft"],
                             "source_ids": record["source_ids"]})
        assert search.status_code == 200
        refusal = client.post(f"/api/cases/{case.id_caso}/assistant", json={"action": "rewrite", "question": "Reescribe mi guion",
                              "draft": record["draft"], "source_ids": record["source_ids"]})
        assert refusal.status_code == 200 and "Sin conexión" in refusal.json()["text"]
        review = client.get(f"/cases/{case.id_caso}/review").text
        version = int(re.search(r'name="expected_version" value="(\d+)"', review).group(1))
        response = client.post(f"/cases/{case.id_caso}/review", data={"state": "en_revision", "actor": "Ensayo G10",
                               "expected_version": version, "note": "Revisión guardada sin red"})
        assert response.status_code == 200
    with server(bundle, destination / "server-restart.log", destination / "isolation-restart.json") as client:
        review = client.get(f"/cases/{case.id_caso}/review").text
        assert "Ensayo G10" in review and "Revisión guardada sin red" in review
        if browser:
            draft = client.get(f"/api/cases/{case.id_caso}/draft").json()["draft"]
            assert draft["titulo"] == "Titular editado durante el ensayo offline G10"
    offline.verify(bundle)
    return {"timestamp_utc": datetime.now(UTC).isoformat(), "counts": counts, "seven_stages": checked,
            "precomputed_queries": queries, "unknown_query_fallback": True, "online_generation_refused": True,
            "review_survives_restart": True, "external_connections_and_local_models": "forbidden; zero attempts",
            "browser": browser_report, "physical_wifi_disabled": False,
            "isolation": "Server refuses non-loopback DNS/socket connections; browser aborts every external origin."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/validation/g10"))
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--bundle", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--audit", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.server:
        guarded_server(args.bundle, args.port, args.audit)
        return
    report = rehearse(args.output.resolve(), browser=args.browser)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
