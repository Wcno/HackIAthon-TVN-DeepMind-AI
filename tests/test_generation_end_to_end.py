"""The whole generation core on the demo set, with a fake model that echoes the demo's own claims."""

import re

from generation_fakes import FakeLLM
from whoami.generation.case_files import TwoStepGenerator, build_outputs
from whoami.generation.prompting import CosineGate
from whoami.generation.retrieval import BM25Index, BM25Retriever, documents_from
from whoami.schemas import verify
from whoami.store import load_demo

MODEL = "gemma-4-26b-a4b-it"
DEMO = load_demo()
PACKAGE_FIELDS = ("titulo", "brief", "enfoque_interes_publico", "preguntas", "fuentes_y_verificaciones", "guion", "copy_digital")


def echo_case(case_file) -> dict:
    data = {
        "afirmaciones": [
            {
                "texto": c.texto,
                "tipo": c.tipo,
                "atribuida_a": c.atribuida_a,
                "citas": [x.model_dump() for x in c.citas],
            }
            for c in case_file.afirmaciones
        ],
    }
    if case_file.borrador is not None:
        data["borrador"] = {name: getattr(case_file.borrador, name) for name in PACKAGE_FIELDS}
        data["borrador"]["preguntas"] = list(case_file.borrador.preguntas)
        data["borrador"]["fuentes_y_verificaciones"] = list(case_file.borrador.fuentes_y_verificaciones)
    return data


def echo_answer(answer) -> dict:
    return {
        "estado": answer.estado,
        "respuesta": answer.respuesta,
        "citas": [c.model_dump() for c in answer.citas],
        "motivo_abstencion": answer.motivo_abstencion,
        "faltante": answer.faltante,
        "versiones": [v.model_dump() for v in answer.versiones],
    }


def demo_model(call: dict):
    """Looks up the demo case by the sources offered, or the demo answer by the question asked."""
    if call["purpose"] == "consulta":
        question = re.search(r"<consulta>(.*)</consulta>", call["messages"][1]["content"]).group(1)
        return echo_answer(next(a for a in DEMO.consultas if a.consulta == question))
    if call["purpose"] == "paquete":
        stated = set(re.findall(r"<afirmacion [^>]*>(.*)</afirmacion>", call["messages"][1]["content"]))
        case_file = next(f for f in DEMO.fichas if stated <= {c.texto for c in f.afirmaciones})
        return echo_case(case_file)["borrador"]
    offered = set(call["evidence_ids"])
    for case_file in DEMO.fichas:
        group = next(g for g in DEMO.grupos if g.id_grupo == case_file.id_grupo)
        if offered == {m.id_noticia for m in group.miembros} | {c.id_evidencia for c in group.contexto}:
            return {"afirmaciones": echo_case(case_file)["afirmaciones"]}
    return {"afirmaciones": []}


QUERIES = [(a.id_consulta, a.consulta) for a in DEMO.consultas]
RETRIEVER = BM25Retriever(BM25Index(documents_from(DEMO.evidencias.values())))
GATE = CosineGate(RETRIEVER, min_cosine=0.5)  # BM25 scores stand in for cosines


def build():
    llm = FakeLLM(demo_model)
    output = build_outputs(
        DEMO,
        TwoStepGenerator(llm, MODEL),
        QUERIES,
        retriever=RETRIEVER,
        gate=GATE,
        llm=llm,
        model=MODEL,
        top_n=len(DEMO.grupos),
    )
    return output, llm


def test_end_to_end_produces_a_set_that_passes_verify():
    output, llm = build()
    verify(output)
    assert {f.id_caso for f in output.fichas} == {f.id_caso for f in DEMO.fichas}
    assert "paquete" in {call["purpose"] for call in llm.calls}


def test_groups_get_their_case_id_and_groups_without_a_case_get_none():
    output, _ = build()
    cases = {g.id_grupo: g.id_caso for g in output.grupos}
    assert cases["G-001"] == "CASO-001" and cases["G-005"] == "CASO-005"
    assert cases["G-006"] is None and cases["G-007"] is None  # the fake model has nothing grounded for them
    assert [g.id_grupo for g in output.grupos] == [g.id_grupo for g in DEMO.grupos]


def test_unverifiable_demo_claims_are_dropped_with_a_gap():
    output, _ = build()
    case_1 = next(f for f in output.fichas if f.id_caso == "CASO-001")
    demo_1 = next(f for f in DEMO.fichas if f.id_caso == "CASO-001")
    assert len(case_1.afirmaciones) < len(demo_1.afirmaciones)  # "Tres medios..." states a figure no source holds
    assert any("afirmación descartada" in gap for gap in case_1.vacios)


def test_the_inflation_contradiction_is_found_by_rules():
    output, _ = build()
    case_2 = next(f for f in output.fichas if f.id_caso == "CASO-002")
    assert {v.valor for c in case_2.contradicciones for v in c.versiones} >= {"1,1 %", "2,3 %"}


def test_only_the_top_n_groups_get_a_case():
    llm = FakeLLM(demo_model)
    output = build_outputs(
        DEMO, TwoStepGenerator(llm, MODEL), [], retriever=RETRIEVER, gate=GATE, llm=llm, model=MODEL, top_n=1
    )
    assert len(output.fichas) == 1 and output.consultas == ()
    assert sum(g.id_caso is not None for g in output.grupos) == 1
    assert all(r.id_caso == output.fichas[0].id_caso for r in output.revisiones)
