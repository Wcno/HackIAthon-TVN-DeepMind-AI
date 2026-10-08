import pytest

from generation_fakes import FakeLLM, LLMError, by_id, group, indicator, member, news
from whoami.contracts import HEADLINE_ONLY_LEGEND
from whoami.generation.case_files import NoGroundedClaims, TwoStepGenerator, generate_case_file
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


def claims(*items):
    return {"afirmaciones": list(items)}


def generator(responses):
    llm = FakeLLM(responses)
    return TwoStepGenerator(llm, MODEL), llm


def test_drops_a_non_literal_claim_and_writes_the_package_from_verified_claims_only():
    gen, llm = generator([claims(GOOD, BAD, OTHER), PACKAGE])
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


def test_fills_gaps_and_action_in_code():
    gen, _ = generator([claims(GOOD), PACKAGE])
    case_file, _, _ = gen.generate(make_group("parcial"), EVIDENCES, "CASO-001")
    assert case_file.vacios and case_file.accion_recomendada


def test_skips_the_package_call_for_an_insufficient_group():
    gen, llm = generator([claims(GOOD)])
    case_file, _, calls = gen.generate(make_group("insuficiente"), EVIDENCES, "CASO-001")
    assert calls == llm.n_calls == 1 and case_file.borrador is None and case_file.vacios


def test_without_grounded_claims_stops_after_the_first_call():
    gen, llm = generator([claims(BAD)])
    with pytest.raises(NoGroundedClaims):
        gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert llm.n_calls == 1


def test_retries_the_package_once_and_then_gives_up():
    gen, llm = generator([claims(GOOD), LONG_PACKAGE, LONG_PACKAGE])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == llm.n_calls == 3
    assert case_file.borrador is None and any("borrador" in gap for gap in case_file.vacios)
    assert "no cumplió los límites" in llm.calls[2]["messages"][0]["content"]


def test_recovers_when_the_retry_is_valid():
    gen, _ = generator([claims(GOOD), LONG_PACKAGE, PACKAGE])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == 3 and case_file.borrador is not None


def test_headline_only_package_carries_the_legend():
    gen, _ = generator([claims(GOOD), PACKAGE])
    case_file, _, _ = gen.generate(make_group(alcance="titular_metadatos"), EVIDENCES, "CASO-001")
    assert case_file.borrador.leyenda == HEADLINE_ONLY_LEGEND


def test_the_claims_call_offers_only_the_sources_of_the_group_and_a_strict_schema():
    gen, llm = generator([claims(GOOD), PACKAGE])
    gen.generate(make_group(), EVIDENCES, "CASO-001")
    call = llm.calls[0]
    assert call["evidence_ids"] == ["N-1", "N-2", "WB-PAN-X-2024"]
    user = call["messages"][1]["content"]
    assert '<fuente id="N-1"' in user and "N-9" not in user
    assert CANARY in call["messages"][0]["content"]
    assert call["response_format"]["json_schema"]["strict"] is True


def test_a_claim_citing_evidence_outside_the_group_is_dropped():
    outside = claim_json("Otra cosa.", pasaje="Otra noticia", id_="N-9", campo="titulo")
    gen, _ = generator([claims(GOOD, outside), PACKAGE])
    case_file, report, _ = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert [c.id_afirmacion for c in case_file.afirmaciones] == ["A-1"]
    assert "A-2" in report.issues


@pytest.mark.parametrize("failure", ["no es json", {"otra": 1}, claims(), LLMError("boom")])
def test_an_unusable_model_answer_means_no_case(failure):
    gen, _ = generator([failure, failure])
    with pytest.raises(NoGroundedClaims):
        gen.generate(make_group(), EVIDENCES, "CASO-001")


def test_a_group_with_some_description_is_not_called_headline_only():
    mixed = group([member("N-1", alcance="titular_descripcion"), member("N-2", "La Prensa", alcance="titular_metadatos")])
    gen, _ = generator([claims(GOOD), PACKAGE])
    case_file, _, _ = gen.generate(mixed, EVIDENCES, "CASO-001")
    assert case_file.alcance_texto == "titular_descripcion"


def test_a_package_that_keeps_failing_becomes_a_gap_not_a_truncation():
    gen, _ = generator([claims(GOOD), LONG_PACKAGE, LONG_PACKAGE])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert calls == 3 and case_file.borrador is None
    assert any("borrador" in gap for gap in case_file.vacios)


def test_a_broken_package_retry_keeps_the_claims_without_draft():
    gen, _ = generator([claims(GOOD, OTHER), LONG_PACKAGE, "no es json", "no es json"])
    case_file, _, calls = gen.generate(make_group(), EVIDENCES, "CASO-001")
    assert case_file.borrador is None and len(case_file.afirmaciones) == 2


def test_contradictions_come_from_the_checker():
    evidences = by_id(
        news("N-1", titulo="La inflación anual fue 1,1 % en septiembre", descripcion=TRANSITS),
        news("N-2", titulo="La inflación anual fue 2,3 % en septiembre"),
        indicator(),
    )
    gen, _ = generator([claims(GOOD), PACKAGE])
    case_file, _, _ = gen.generate(make_group(), evidences, "CASO-001")
    assert len(case_file.contradicciones) == 1


def test_a_sufficient_group_may_have_no_gaps():
    gen, _ = generator([claims(GOOD), PACKAGE])
    case_file, _, _ = gen.generate(make_group("suficiente_para_borrador"), EVIDENCES, "CASO-001")
    assert case_file.vacios == ()


def test_an_insufficient_group_asks_for_no_package():
    gen, llm = generator([claims(GOOD)])
    gen.generate(make_group("insuficiente"), EVIDENCES, "CASO-001")
    assert [call["purpose"] for call in llm.calls] == ["afirmaciones"]


def test_a_cap_reached_during_the_package_call_is_not_swallowed():
    from whoami.llm.client import CapExceeded

    class CapOnSecondCall:
        def __init__(self):
            self.calls = 0

        def complete(self, *args, **kwargs):
            self.calls += 1
            if self.calls > 1:
                raise CapExceeded("tope")
            return FakeLLM([claims(GOOD)]).complete(*args, **kwargs)

    with pytest.raises(CapExceeded):
        TwoStepGenerator(CapOnSecondCall(), "m").generate(make_group(), EVIDENCES, "CASO-001")


def test_generate_case_file_builds_one_group_with_the_id_derived_from_the_group():
    gen, llm = generator([claims(GOOD), PACKAGE])
    case_file = generate_case_file(gen, make_group(), EVIDENCES)
    assert case_file.id_caso == "CASO-1" and case_file.id_grupo == "G-1"
    assert llm.n_calls == 2


def test_generate_case_file_keeps_the_case_id_a_group_already_has():
    gen, _ = generator([claims(GOOD), PACKAGE])
    existing = make_group().model_copy(update={"id_caso": "CASO-777"})
    assert generate_case_file(gen, existing, EVIDENCES).id_caso == "CASO-777"


def test_generate_case_file_lets_no_grounded_claims_reach_the_caller():
    gen, _ = generator([claims(BAD)])
    with pytest.raises(NoGroundedClaims):
        generate_case_file(gen, make_group(), EVIDENCES)


def test_generate_case_file_for_an_insufficient_group_is_a_case_without_draft():
    gen, llm = generator([claims(GOOD)])
    case_file = generate_case_file(gen, make_group(estado="insuficiente"), EVIDENCES)
    assert case_file.borrador is None and llm.n_calls == 1
