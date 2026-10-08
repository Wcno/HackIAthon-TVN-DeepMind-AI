"""`whoami generar` on the demo data copied to a tmp dir, with a fake model and a fake embedder."""

import json
import shutil
import sys

import numpy as np
import pytest

from generation_fakes import FakeLLM
from test_generation_end_to_end import DEMO, demo_model
from whoami import cli
from whoami.contracts import DEMO as DEMO_DIR
from whoami.contracts import EVIDENCE_FILE, FICHAS_FILE, GROUPS_FILE, QUERIES_FILE, REVIEWS_FILE
from whoami.generation import run
from whoami.generation.run import RunConfig
from whoami.schemas import sort_inbox, verify
from whoami.store import load, read_jsonl

MODEL = "gemma-4-26b-a4b-it"
STATES = {g.id_grupo: g.estado_evidencia for g in DEMO.grupos}
#: Topics TVN covered drop out, except the one insufficient case file, which ignores coverage (CASO-003 here).
EXPECTED_FICHAS = [f for f in DEMO.fichas if f.id_caso in {"CASO-001", "CASO-002", "CASO-003", "CASO-005"}]


class FakeEmbedder:
    """Queries and documents live in one fixed direction (cosine 1) or in orthogonal ones (cosine 0)."""

    def __init__(self, related: bool) -> None:
        self._related = related

    def embed_documents(self, texts):
        return np.tile([1.0, 0.0], (len(texts), 1))

    def embed_queries(self, texts):
        return np.tile([1.0, 0.0] if self._related else [0.0, 1.0], (len(texts), 1))


@pytest.fixture
def workspace(tmp_path):
    data, outputs = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    outputs.mkdir()
    for name in (GROUPS_FILE, EVIDENCE_FILE):
        shutil.copy(DEMO_DIR / name, data / name)
    shutil.copy(DEMO_DIR / REVIEWS_FILE, outputs / REVIEWS_FILE)
    shutil.copy(DEMO_DIR / FICHAS_FILE, outputs / FICHAS_FILE)
    queries = tmp_path / "consultas.jsonl"
    queries.write_text(
        "".join(json.dumps({"id": a.id_consulta, "consulta": a.consulta, "tipo": "demo"}) + "\n" for a in DEMO.consultas),
        encoding="utf-8",
    )
    return data, outputs, queries


def config(queries, **overrides):
    values = dict(modelo=MODEL, top=len(DEMO.grupos), consultas=queries, implicacion=False)
    return RunConfig(**values | overrides)


def generar(workspace, related=True, **overrides):
    data, outputs, queries = workspace
    llm = FakeLLM(demo_model)
    summary = run.generar(config(queries, **overrides), llm, FakeEmbedder(related), data, outputs)
    return summary, llm, data, outputs


def test_the_written_output_loads_and_passes_verify(workspace):
    _, _, data, outputs = generar(workspace)
    written = load(data, outputs)
    verify(written)
    assert {f.id_caso for f in written.fichas} == {f.id_caso for f in EXPECTED_FICHAS}
    assert [a.estado for a in written.consultas] == [a.estado for a in DEMO.consultas]
    assert {g.id_grupo: g.id_caso for g in written.grupos}["G-001"] == "CASO-001"
    assert (outputs / FICHAS_FILE).exists() and (outputs / QUERIES_FILE).exists()


def test_previous_review_history_is_kept_without_approving_regenerated_content(workspace):
    _, _, data, outputs = generar(workspace)
    written = load(data, outputs)
    assert not written.revisiones
    assert written.historial_revisiones
    assert all(written.review_state(case.id_caso) == "nuevo" for case in written.fichas)
    assert any(snapshot.decisiones[-1].estado == "aprobado_como_borrador" for snapshot in written.historial_revisiones)


def test_generar_reloads_bound_reviews_and_preserves_all_archives_across_runs(workspace):
    from whoami.store import write
    data, outputs, queries = workspace
    write(DEMO, data, outputs)
    first, _, _, _ = generar(workspace)
    previous = load(data, outputs)
    assert previous.review_state("CASO-005") == "nuevo"
    assert previous.historial_revisiones
    generar(workspace)
    current = load(data, outputs)
    assert current.historial_revisiones == previous.historial_revisiones
    assert current.review_state("CASO-005") == "nuevo"


def test_a_missing_reviews_file_is_an_empty_history(workspace):
    data, outputs, _ = workspace
    (outputs / REVIEWS_FILE).unlink()
    generar(workspace)
    assert load(data, outputs).revisiones == ()


def test_the_cosine_gate_abstains_without_calling_the_model_when_nothing_resembles_the_query(workspace):
    _, llm, data, outputs = generar(workspace, related=False)
    answers = load(data, outputs).consultas
    assert {a.estado for a in answers} == {"abstencion"}
    assert "consulta" not in {call["purpose"] for call in llm.calls}


def test_the_summary_counts_cases_claims_packages_answers_and_calls(workspace):
    summary, llm, _, _ = generar(workspace)
    assert summary.fichas == len(EXPECTED_FICHAS)
    assert summary.afirmaciones_conservadas > 0 and summary.afirmaciones_descartadas > 0
    assert summary.paquetes == sum(f.borrador is not None for f in EXPECTED_FICHAS)
    assert summary.respuestas == {"respondida": 2, "contradiccion": 1, "abstencion": 1}
    assert summary.llamadas["afirmaciones"] == {"hit": 0, "miss": sum(c["purpose"] == "afirmaciones" for c in llm.calls)}
    text = summary.render()
    assert "respondida: 2" in text and "afirmaciones" in text


def test_insufficient_groups_do_not_take_top_slots_but_one_is_kept_as_the_case_without_enough_evidence(workspace):
    _, _, data, outputs = generar(workspace, top=3)  # the third group of the inbox is insufficient
    written = load(data, outputs)
    assert {f.id_caso for f in written.fichas} == {"CASO-001", "CASO-002", "CASO-005", "CASO-003"}
    assert [f.borrador for f in written.fichas if STATES[f.id_grupo] == "insuficiente"] == [None]


def test_the_implication_check_runs_through_the_command(workspace):
    def model(call):
        if call["purpose"] == "g4-implicacion":
            return {"veredicto": "respaldada", "motivo": "ok"}
        return demo_model(call)

    data, outputs, queries = workspace
    llm = FakeLLM(model)
    run.generar(config(queries, implicacion=True), llm, FakeEmbedder(True), data, outputs)
    purposes = {call["purpose"] for call in llm.calls}
    assert {"afirmaciones", "paquete", "g4-implicacion"} <= purposes
    verify(load(data, outputs))


def test_queries_file_needs_id_and_text_and_ignores_the_rest(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text('{"id": "D-1", "consulta": "¿Qué?", "tipo": "x", "nota": "y"}\n\n{"id": "D-2", "consulta": "¿Cómo?"}\n', encoding="utf-8")
    assert run.load_queries(path) == [("D-1", "¿Qué?"), ("D-2", "¿Cómo?")]


def run_cli(workspace, monkeypatch, *extra):
    data, outputs, queries = workspace
    llm = FakeLLM(demo_model)
    monkeypatch.setattr(run, "default_llm", lambda: llm)
    monkeypatch.setattr(run, "LocalEmbedder", lambda: FakeEmbedder(True))
    monkeypatch.setattr(run, "PROCESSED", data)
    monkeypatch.setattr(run, "OUTPUTS", outputs)
    monkeypatch.setattr(run.manifest, "refresh", lambda paths: None)  # the real manifest is not a test fixture
    monkeypatch.setattr(sys, "argv", ["whoami", "generar", "--consultas", str(queries), *extra])
    assert cli.main() == 0
    verify(load(data, outputs))
    return llm


def test_the_command_checks_entailment_by_default(workspace, monkeypatch, capsys):
    llm = run_cli(workspace, monkeypatch)
    assert "g4-implicacion" in {call["purpose"] for call in llm.calls}
    assert "fichas" in capsys.readouterr().out


def test_sin_implicacion_turns_the_entailment_check_off(workspace, monkeypatch):
    llm = run_cli(workspace, monkeypatch, "--sin-implicacion")
    assert "g4-implicacion" not in {call["purpose"] for call in llm.calls}


def test_the_default_model_is_the_production_one():
    assert run.DEFAULT_MODEL == "gemini-3.5-flash-lite"


def test_the_demo_queries_file_has_the_non_synthetic_devset_queries():
    rows = read_jsonl(run.DEFAULT_QUERIES)
    ids = {r["id"] for r in rows}
    assert len(rows) == len(ids) == 35
    assert not ids & {"D-C08", "D-C09", "D-C10", "D-X03", "D-X08"}
    assert all(set(r) == {"id", "consulta", "tipo", "nota"} for r in rows)
    assert {r["nota"] for r in rows} == {"conjunto de desarrollo, no es el benchmark reservado"}
