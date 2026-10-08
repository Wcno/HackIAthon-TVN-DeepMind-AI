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
        answer = echo_answer(next(a for a in DEMO.consultas if a.consulta == question))
        for version in answer["versiones"]:
            source = DEMO.evidencias[version["id_evidencia"]]
            version["alcance"] = source.campos.get("descripcion", source.campos["titulo"])
        return answer
    if call["purpose"] == "paquete":
        stated = set(re.findall(r"<afirmacion [^>]*>(.*)</afirmacion>", call["messages"][1]["content"]))
        case_file = next(f for f in DEMO.fichas if stated <= {c.texto for c in f.afirmaciones})
        ids = re.findall(r'<afirmacion id="([^"]+)"', call["messages"][1]["content"])
        return {"titulo": ids[:1], "brief": ids, "guion": ids, "copy_digital": ids[:1],
                "enfoque": "verificacion", "preguntas": ["fuentes", "vacios", "actualizaciones"]}
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


def test_regenerating_approved_content_revokes_only_its_active_cycle(tmp_path):
    from whoami.store import write, load
    from whoami.backend.pipeline import load_pipeline
    from whoami.backend.repository import EditorialRepository
    original = next(case for case in DEMO.fichas if case.id_caso == "CASO-005")
    assert DEMO.review_state(original.id_caso) == "aprobado_como_borrador"
    class Changed:
        def generate(self, group, evidence, case_id):
            case = next(c for c in DEMO.fichas if c.id_grupo == group.id_grupo)
            if case.id_caso == original.id_caso:
                case = case.model_copy(update={"accion_recomendada": "Una nueva decision pendiente de revision"})
            return case, None, 0
    output = build_outputs(DEMO, Changed(), [], retriever=RETRIEVER, gate=GATE,
                           llm=FakeLLM([]), model=MODEL, top_n=5)
    assert output.review_state(original.id_caso) == "nuevo"
    write(output, tmp_path / "data", tmp_path / "out")
    restored = load(tmp_path / "data", tmp_path / "out")
    assert restored.review_state(original.id_caso) == "nuevo"
    repo = EditorialRepository(tmp_path / "fresh.sqlite3")
    repo.import_bundle(load_pipeline(tmp_path / "data", tmp_path / "out"))
    assert repo.case(original.id_caso)["estado_revision"] == "nuevo"
    assert any(r["estado"] == "aprobado_como_borrador" for r in repo.review_history(original.id_caso))


def test_source_change_revokes_approval_and_keeps_the_original_reviewed_snapshot(tmp_path):
    from whoami.store import write, load
    write(DEMO, tmp_path / "data", tmp_path / "out")
    reviewed = load(tmp_path / "data", tmp_path / "out")
    original = next(case for case in reviewed.fichas if case.id_caso == "CASO-005")
    source_id = original.cited_ids[0]
    source = reviewed.evidencias[source_id]
    amended = source.model_copy(update={"campos": source.campos | {"correccion": "Nueva información pendiente de revisión"}})
    changed = reviewed.model_copy(update={"evidencias": reviewed.evidencias | {source_id: amended}})
    class Unchanged:
        def generate(self, group, evidence, case_id):
            return next(c for c in reviewed.fichas if c.id_grupo == group.id_grupo), None, 0
    output = build_outputs(changed, Unchanged(), [], retriever=RETRIEVER, gate=GATE,
                           llm=FakeLLM([]), model=MODEL, top_n=5)
    assert output.review_state(original.id_caso) == "nuevo"
    archive = next(item for item in output.historial_revisiones if item.ficha.id_caso == original.id_caso)
    assert archive.evidencias[source_id] == source
    assert archive.decisiones[-1].estado == "aprobado_como_borrador"


def test_unchanged_bound_content_preserves_its_review_cycle(tmp_path):
    from whoami.store import write, load
    class Unchanged:
        def generate(self, group, evidence, case_id):
            return next(c for c in DEMO.fichas if c.id_grupo == group.id_grupo), None, 0
    generator = Unchanged()
    assessed = build_outputs(DEMO, generator, [], retriever=RETRIEVER, gate=GATE,
                             llm=FakeLLM([]), model=MODEL, top_n=5)
    reviews = tuple(r for r in DEMO.revisiones if r.id_caso == "CASO-005")
    reviewed = assessed.model_copy(update={"revisiones": reviews})
    write(reviewed, tmp_path / "data", tmp_path / "out")
    reviewed = load(tmp_path / "data", tmp_path / "out")
    output = build_outputs(reviewed, generator, [], retriever=RETRIEVER, gate=GATE,
                           llm=FakeLLM([]), model=MODEL, top_n=5)
    assert output.review_state("CASO-005") == "aprobado_como_borrador"
    assert output.revisiones == reviews
    assert output.historial_revisiones == reviewed.historial_revisiones


def test_loading_changed_sources_cannot_import_stale_approval_into_fresh_database(tmp_path):
    from whoami.store import write, load, write_jsonl
    from whoami.backend.pipeline import load_pipeline
    from whoami.backend.repository import EditorialRepository
    write(DEMO, tmp_path / "data", tmp_path / "out")
    source_id = next(c for c in DEMO.fichas if c.id_caso == "CASO-005").cited_ids[0]
    amended = DEMO.evidencias[source_id].model_copy(update={"titulo": "Corrección de la fuente"})
    write_jsonl(tmp_path / "data" / "evidencias.jsonl", [
        (amended if identity == source_id else source).model_dump(mode="json")
        for identity, source in DEMO.evidencias.items()
    ])
    output = load(tmp_path / "data", tmp_path / "out")
    assert output.review_state("CASO-005") == "nuevo"
    repo = EditorialRepository(tmp_path / "fresh.sqlite3")
    repo.import_bundle(load_pipeline(tmp_path / "data", tmp_path / "out"))
    assert repo.case("CASO-005")["estado_revision"] == "nuevo"
    assert any(r["estado"] == "aprobado_como_borrador" for r in repo.review_history("CASO-005"))


def test_end_to_end_produces_a_set_that_passes_verify():
    output, llm = build()
    verify(output)
    assert {f.id_caso for f in output.fichas} == {"CASO-001", "CASO-002", "CASO-005"}
    assert all(g.cobertura_tvn.estado != "cubierto" for g in output.grupos if g.id_caso)
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
