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
#: The command skips insufficient groups in the top but keeps one: the best ranked, which has a demo case file.
BEST_INSUFFICIENT = next(g for g in sort_inbox(DEMO.grupos) if g.estado_evidencia == "insuficiente")
EXPECTED_FICHAS = [f for f in DEMO.fichas if STATES[f.id_grupo] != "insuficiente" or f.id_grupo == BEST_INSUFFICIENT.id_grupo]


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


def test_the_review_history_of_generated_cases_is_kept(workspace):
    _, _, data, outputs = generar(workspace)
    written = load(data, outputs)
    assert written.revisiones and {r.id_caso for r in written.revisiones} <= {f.id_caso for f in written.fichas}


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
