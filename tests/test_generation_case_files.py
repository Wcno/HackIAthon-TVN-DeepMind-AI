import pytest

from generation_fakes import FakeLLM, LLMError, by_id, group, indicator, member, news
from whoami.contracts import HEADLINE_ONLY_LEGEND
from whoami.generation.case_files import NoGroundedClaims, SingleShotGenerator, TwoStepGenerator
from whoami.generation.prompting import CANARY
from whoami.schemas import ContextLink

TRANSITS = "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios a partir del 12 de octubre."
EVIDENCES = by_id(
    news("N-1", titulo="El Canal reduce los tránsitos diarios", descripcion=TRANSITS),
    news("N-2", titulo="El Canal limita los tránsitos por la sequía"),
    news("N-9", titulo="Otra noticia sin relación con el grupo"),
    indicator(),
)
CONTEXT = (ContextLink(id_evidencia="WB-PAN-X-2024", etiqueta="Exportaciones", pais="Panamá", limitaciones="Dato anual", razon="Contexto"),)
MODEL = "gemma-4-26b-a4b-it"


def make_group(estado="parcial", alcance="titular_descripcion", context=CONTEXT):
    return group(
        [member("N-1", "TVN", alcance=alcance), member("N-2", "La Prensa", alcance=alcance)], estado=estado, context=context
    )


def claim_json(text="El Canal limitará a 32 los tránsitos diarios.", pasaje="limitará a 32 los tránsitos diarios", id_="N-1", campo="descripcion", tipo="hecho", author=None):
    return {"texto": text, "tipo": tipo, "atribuida_a": author, "citas": [{"id_evidencia": id_, "campo": campo, "pasaje": pasaje}]}


GOOD = claim_json()
BAD = claim_json("El Canal cerrará el lago Gatún.", pasaje="el Canal cerrará todo el lago Gatún")
OTHER = claim_json("El Canal limita los tránsitos.", pasaje="limita los tránsitos", id_="N-2", campo="titulo")

PACKAGE = {
    "titulo": "El Canal limita tránsitos",
    "brief": "El Canal informó una restricción de tránsitos.",
    "enfoque_interes_publico": "Efecto en el comercio.",
    "preguntas": ["¿Cuánto durará?", "¿Quién se afecta?", "¿Qué medidas hay?"],
    "fuentes_y_verificaciones": ["Confirmar con el comunicado."],
    "guion": "El Canal limitará los tránsitos.",
    "copy_digital": "El Canal limita tránsitos.",
}
LONG_PACKAGE = PACKAGE | {"copy_digital": " ".join(["palabra"] * 81)}


def single(claims=(GOOD, OTHER), package=PACKAGE, vacios=("Falta el comunicado.",), accion="Pedir el comunicado."):
    data = {"afirmaciones": list(claims), "vacios": list(vacios), "accion_recomendada": accion}
    return data | ({"borrador": package} if package is not None else {})


def generator(responses, kind=SingleShotGenerator):
    llm = FakeLLM(responses)
    return kind(llm, MODEL), llm


# ---------------------------------------------------------------------------------------------------------
# Single shot
# ---------------------------------------------------------------------------------------------------------


def test_single_shot_builds_the_case_file_in_one_call():
    gen, llm = generator([single()])
    case_file, report, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == llm.n_calls == 1
    assert (case_file.id_caso, case_file.id_grupo, case_file.alcance_texto) == ("CASO-001", "G-1", "titular_descripcion")
    assert [c.id_afirmacion for c in case_file.afirmaciones] == ["A-1", "A-2"]
    assert case_file.vacios == ("Falta el comunicado.",)
    assert case_file.accion_recomendada == "Pedir el comunicado."
    assert case_file.borrador.titulo == "El Canal limita tránsitos" and case_file.borrador.leyenda is None
    assert len(report.valid_claims) == 2 and not report.issues


def test_the_call_offers_only_the_sources_of_the_group_and_a_strict_schema():
    gen, llm = generator([single()])
    gen.generate(make_group(), EVIDENCES, "CASO-001")
    call = llm.calls[0]
    assert call["purpose"] == "ficha"
    assert call["evidence_ids"] == ["N-1", "N-2", "WB-PAN-X-2024"]
    user = call["messages"][1]["content"]
    assert '<fuente id="N-1"' in user and "N-9" not in user
    assert CANARY in call["messages"][0]["content"]
    schema = call["response_format"]["json_schema"]
    assert schema["strict"] is True and "borrador" in schema["schema"]["properties"]


def test_a_claim_with_a_non_literal_passage_is_dropped_and_leaves_a_gap():
    gen, _ = generator([single(claims=(GOOD, BAD, OTHER))])
    case_file, report, _ = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert [c.id_afirmacion for c in case_file.afirmaciones] == ["A-1", "A-3"]
    assert "afirmación descartada por cita no verificable (A-2)" in case_file.vacios
    assert list(report.issues) == ["A-2"]


def test_a_claim_citing_evidence_outside_the_group_is_dropped():
    outside = claim_json("Otra cosa.", pasaje="Otra noticia", id_="N-9", campo="titulo")
    gen, _ = generator([single(claims=(GOOD, outside))])
    case_file, report, _ = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert [c.id_afirmacion for c in case_file.afirmaciones] == ["A-1"]
    assert "A-2" in report.issues


def test_without_any_grounded_claim_the_case_is_not_generated():
    gen, _ = generator([single(claims=(BAD,))])
    with pytest.raises(NoGroundedClaims):
        gen.generate(make_group(), EVIDENCES, "CASO-001")


@pytest.mark.parametrize("failure", ["no es json", {"otra": 1}, {"afirmaciones": []}, LLMError("boom")])
def test_an_unusable_model_answer_means_no_case(failure):
    gen, _ = generator([failure, failure])
    with pytest.raises(NoGroundedClaims):
        gen.generate(make_group(), EVIDENCES, "CASO-001")


def test_an_insufficient_group_gets_no_draft_and_the_schema_does_not_ask_for_one():
    gen, llm = generator([single(package=None, vacios=())])
    case_file, _, calls = gen.generate(make_group("insuficiente"), EVIDENCES, "CASO-001")
    assert case_file.borrador is None and calls == 1
    assert "borrador" not in llm.calls[0]["response_format"]["json_schema"]["schema"]["properties"]
    assert case_file.vacios, "an insufficient case must say what is missing"


def test_headline_only_groups_carry_the_legend():
    gen, _ = generator([single()])
    case_file, _, _ = gen.generate(make_group(alcance="titular_metadatos"), EVIDENCES, "CASO-001")
    assert case_file.alcance_texto == "titular_metadatos"
    assert case_file.borrador.leyenda == HEADLINE_ONLY_LEGEND


def test_a_group_with_some_description_is_not_called_headline_only():
    mixed = group([member("N-1", alcance="titular_descripcion"), member("N-2", "La Prensa", alcance="titular_metadatos")])
    gen, _ = generator([single()])
    case_file, _, _ = gen.generate(mixed, EVIDENCES, "CASO-001")
    assert case_file.alcance_texto == "titular_descripcion"


def test_a_package_over_the_limits_is_retried_once_with_the_error():
    gen, llm = generator([single(package=LONG_PACKAGE), single()])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == 2 and case_file.borrador is not None
    assert "no cumplió los límites" in llm.calls[1]["messages"][0]["content"]
    assert "copy_digital" in llm.calls[1]["messages"][0]["content"]
    assert "no cumplió los límites" not in llm.calls[0]["messages"][0]["content"]


def test_a_package_that_keeps_failing_becomes_a_gap_not_a_truncation():
    gen, _ = generator([single(package=LONG_PACKAGE), single(package=LONG_PACKAGE)])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == 2 and case_file.borrador is None
    assert any("borrador" in gap for gap in case_file.vacios)


def test_a_broken_retry_keeps_the_first_claims_without_draft():
    gen, _ = generator([single(package=LONG_PACKAGE), "no es json", "no es json"])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == 2 and case_file.borrador is None and len(case_file.afirmaciones) == 2


def test_contradictions_come_from_the_checker():
    evidences = by_id(
        news("N-1", titulo="La inflación anual fue 1,1 % en septiembre", descripcion=TRANSITS),
        news("N-2", titulo="La inflación anual fue 2,3 % en septiembre"),
        indicator(),
    )
    gen, _ = generator([single(claims=(GOOD,))])
    case_file, _, _ = gen.generate(make_group(), evidences, "CASO-001")
    assert len(case_file.contradicciones) == 1


def test_a_group_that_is_not_sufficient_always_lists_a_gap():
    gen, _ = generator([single(vacios=())])
    case_file, _, _ = gen.generate(make_group("parcial"), EVIDENCES, "CASO-001")
    assert case_file.vacios


def test_a_sufficient_group_may_have_no_gaps():
    gen, _ = generator([single(vacios=())])
    case_file, _, _ = gen.generate(make_group("suficiente_para_borrador"), EVIDENCES, "CASO-001")
    assert case_file.vacios == ()


# ---------------------------------------------------------------------------------------------------------
# Two step
# ---------------------------------------------------------------------------------------------------------


def test_two_step_drops_a_non_literal_claim_and_writes_the_package_from_verified_claims_only():
    gen, llm = generator([{"afirmaciones": [GOOD, BAD, OTHER]}, PACKAGE], kind=TwoStepGenerator)
    case_file, report, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == llm.n_calls == 2
    assert [c.id_afirmacion for c in case_file.afirmaciones] == ["A-1", "A-3"]
    assert "afirmación descartada por cita no verificable (A-2)" in case_file.vacios
    assert list(report.issues) == ["A-2"]
    claims_call, package_call = llm.calls
    assert claims_call["purpose"] == "afirmaciones" and package_call["purpose"] == "paquete"
    assert set(claims_call["response_format"]["json_schema"]["schema"]["properties"]) == {"afirmaciones"}
    user = package_call["messages"][1]["content"]
    assert "<fuente" not in user
    assert "El Canal limitará a 32 los tránsitos diarios." in user and "cerrará el lago" not in user
    assert case_file.borrador.titulo == PACKAGE["titulo"]


def test_two_step_fills_gaps_and_action_in_code():
    gen, _ = generator([{"afirmaciones": [GOOD]}, PACKAGE], kind=TwoStepGenerator)
    case_file, _, _ = gen.generate(make_group("parcial"), EVIDENCES, "CASO-001")
    assert case_file.vacios and case_file.accion_recomendada


def test_two_step_skips_the_package_call_for_an_insufficient_group():
    gen, llm = generator([{"afirmaciones": [GOOD]}], kind=TwoStepGenerator)
    case_file, _, calls = gen.generate(make_group("insuficiente"), EVIDENCES, "CASO-001")
    assert calls == llm.n_calls == 1 and case_file.borrador is None and case_file.vacios


def test_two_step_without_grounded_claims_stops_after_the_first_call():
    gen, llm = generator([{"afirmaciones": [BAD]}], kind=TwoStepGenerator)
    with pytest.raises(NoGroundedClaims):
        gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert llm.n_calls == 1


def test_two_step_retries_the_package_once_and_then_gives_up():
    gen, llm = generator([{"afirmaciones": [GOOD]}, LONG_PACKAGE, LONG_PACKAGE], kind=TwoStepGenerator)
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == llm.n_calls == 3
    assert case_file.borrador is None and any("borrador" in gap for gap in case_file.vacios)
    assert "no cumplió los límites" in llm.calls[2]["messages"][0]["content"]


def test_two_step_recovers_when_the_retry_is_valid():
    gen, _ = generator([{"afirmaciones": [GOOD]}, LONG_PACKAGE, PACKAGE], kind=TwoStepGenerator)
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == 3 and case_file.borrador is not None


def test_two_step_headline_only_package_carries_the_legend():
    gen, _ = generator([{"afirmaciones": [GOOD]}, PACKAGE], kind=TwoStepGenerator)
    case_file, _, _ = gen.generate(make_group(alcance="titular_metadatos"), EVIDENCES, "CASO-001")
    assert case_file.borrador.leyenda == HEADLINE_ONLY_LEGEND


def test_a_cap_reached_during_the_package_retry_is_not_swallowed():
    import pytest
    from whoami.generation.case_files import SingleShotGenerator
    from whoami.llm.client import CapExceeded
    from whoami.store import load_demo

    output = load_demo()
    group = next(g for g in output.grupos if g.id_grupo == "G-001")
    over_limit = {"afirmaciones": [{"texto": "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios", "tipo": "hecho", "atribuida_a": None,
                   "citas": [{"id_evidencia": "N-2cf673d2b74a", "campo": "descripcion", "pasaje": "limitará a 32 los tránsitos diarios"}]}],
                  "vacios": [], "accion_recomendada": "Verificar.",
                  "borrador": {"titulo": "t", "brief": "palabra " * 300, "enfoque_interes_publico": "e", "preguntas": ["a", "b", "c"],
                               "fuentes_y_verificaciones": [], "guion": "g", "copy_digital": "c"}}

    class CapOnSecondCall:
        def __init__(self):
            self.calls = 0

        def complete(self, *args, **kwargs):
            self.calls += 1
            if self.calls > 1:
                raise CapExceeded("tope")
            import json
            from types import SimpleNamespace
            return SimpleNamespace(json=lambda: over_limit, cached=False, text=json.dumps(over_limit))

    with pytest.raises(CapExceeded):
        SingleShotGenerator(CapOnSecondCall(), "m").generate(group, output.evidencias, "CASO-001")
