import math

import pytest
from pydantic import ValidationError

from whoami.schemas import (
    Answer,
    CaseFile,
    Citation,
    Claim,
    Components,
    ContextLink,
    Contradiction,
    ContradictionVersion,
    EditorialPackage,
    Evidence,
    Group,
    Member,
    OutputSet,
    ReviewRecord,
    Score,
    citation_errors,
    compute_score,
    current_review_state,
    parse_utc,
    range_of,
    sort_inbox,
    verify,
)

HEADLINE_LEGEND = "basado únicamente en titular/metadatos"


def components(R=0.0, I=0.0, U=0.0, N=0.0, E=0.0) -> Components:
    return Components(R=R, I=I, U=U, N=N, E=E)


# §4: P = 30R + 25I + 20U + 15N + 10E, each component in 0-1.
@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (dict(R=1, I=1, U=1, N=1, E=1), 100.0),
        (dict(), 0.0),
        (dict(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), 71.5),  # 24 + 15 + 20 + 7.5 + 5
        (dict(R=0.25, N=1.0), 22.5),  # 7.5 + 15
    ],
)
def test_score_follows_the_weighted_formula(values, expected):
    assert compute_score(components(**values)) == expected


@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan, math.inf])
def test_components_outside_zero_one_are_rejected(bad):
    with pytest.raises(ValueError, match="R"):
        components(R=bad)


# §4: bajo [0,40), medio [40,70), alto [70,100], no overlap.
@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "bajo"), (39.99, "bajo"), (40, "medio"), (69.99, "medio"), (70, "alto"), (100, "alto")],
)
def test_range_boundaries_do_not_overlap(value, expected):
    assert range_of(value) == expected


@pytest.mark.parametrize("outside", [-0.1, 100.01, math.nan])
def test_range_rejects_values_outside_zero_hundred(outside):
    with pytest.raises(ValueError):
        range_of(outside)


JUSTIFICATIONS = {
    "R": "Afecta el tránsito por el Canal.",
    "I": "Alcance sectorial.",
    "U": "Publicado hace menos de 24 h.",
    "N": "Evento nuevo.",
    "E": "Dos procedencias distintas.",
}


def test_score_is_computed_from_components_never_supplied():
    score = Score.from_components(components(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), JUSTIFICATIONS)

    assert (score.valor, score.rango) == (71.5, "alto")
    assert score.version_reglas == "1.0.0"


def score_fields(**changes) -> dict:
    fields = dict(
        componentes=components(R=1, I=1, U=1, N=1, E=1),
        valor=100.0,
        rango="alto",
        version_reglas="1.0.0",
        justificaciones=JUSTIFICATIONS,
    )
    return fields | changes


def test_a_score_whose_value_does_not_match_its_components_is_rejected():
    with pytest.raises(ValueError, match="valor"):
        Score(**score_fields(valor=55.0, rango="medio"))


def test_a_score_whose_range_does_not_match_its_value_is_rejected():
    with pytest.raises(ValueError, match="rango"):
        Score(**score_fields(rango="bajo"))


@pytest.mark.parametrize("missing", ["R", "E"])
def test_every_component_needs_a_justification(missing):
    incomplete = {k: v for k, v in JUSTIFICATIONS.items() if k != missing}

    with pytest.raises(ValueError, match=missing):
        Score.from_components(components(R=1), incomplete)


def evidence(**changes) -> Evidence:
    fields = dict(
        id_evidencia="N-af71800f62ff",
        tipo="noticia",
        titulo="El Canal reduce los tránsitos diarios por la sequía",
        url="https://ejemplo.test/canal",
        fecha=parse_utc("2026-10-05T14:00:00Z"),
        campos={"titulo": "El Canal reduce los tránsitos diarios por la sequía", "descripcion": "Pasan de 36 a 32 buques."},
    )
    return Evidence(**(fields | changes))


def test_evidence_id_prefix_must_match_its_type():
    with pytest.raises(ValueError, match="id_evidencia"):
        evidence(id_evidencia="WB-PAN-NY.GDP.MKTP.KD.ZG-2023")


@pytest.mark.parametrize("date", ["2026-10-05", "2026-10-05T14:00:00-05:00", "2026-13-45T99:00:00Z", "ayer"])
def test_evidence_dates_must_be_real_iso_8601_utc(date):
    with pytest.raises(ValueError, match="fecha"):
        evidence(fecha=date)


def test_values_of_the_wrong_type_are_rejected_when_loading():
    record = evidence().model_dump(mode="json")

    with pytest.raises(ValidationError, match="titulo"):
        Evidence.model_validate(record | {"titulo": 123})
    with pytest.raises(ValidationError, match="campo"):
        Citation.model_validate({"id_evidencia": "N-af71800f62ff", "campo": 5, "pasaje": "x"})
    with pytest.raises(ValidationError, match="campos"):
        Evidence.model_validate(record | {"campos": {"titulo": 7}})


def test_unknown_fields_are_rejected_when_loading():
    record = evidence().model_dump(mode="json")

    with pytest.raises(ValidationError, match="atribuida"):
        Evidence.model_validate(record | {"atribuida": "x"})


def test_a_citation_resolves_only_to_a_literal_passage_of_an_existing_field():
    registry = {"N-af71800f62ff": evidence()}
    good = Citation(id_evidencia="N-af71800f62ff", campo="descripcion", pasaje="de 36 a 32 buques")

    assert citation_errors([good], registry) == []


@pytest.mark.parametrize(
    ("citation", "fragment"),
    [
        (Citation(id_evidencia="N-000000000000", campo="titulo", pasaje="Canal"), "no existe"),
        (Citation(id_evidencia="N-af71800f62ff", campo="cuerpo", pasaje="Canal"), "campo"),
        (Citation(id_evidencia="N-af71800f62ff", campo="descripcion", pasaje="de 36 a 30 buques"), "literal"),
    ],
)
def test_citations_that_do_not_resolve_are_reported(citation, fragment):
    errors = citation_errors([citation], {"N-af71800f62ff": evidence()})

    assert len(errors) == 1 and fragment in errors[0]


CITATION = Citation(id_evidencia="N-af71800f62ff", campo="titulo", pasaje="reduce los tránsitos")


def claim(**changes) -> Claim:
    fields = dict(
        id_afirmacion="A-1",
        texto="El Canal reduce los tránsitos.",
        tipo="hecho",
        citas=(CITATION,),
        atribuida_a=None,
    )
    return Claim(**(fields | changes))


def test_every_claim_needs_at_least_one_citation():
    with pytest.raises(ValueError, match="citas"):
        claim(citas=())


def test_claim_type_must_be_one_of_the_four_the_challenge_distinguishes():
    with pytest.raises(ValueError, match="tipo"):
        claim(tipo="rumor")


def test_a_statement_must_say_who_made_it():
    with pytest.raises(ValueError, match="atribuida_a"):
        claim(texto="La ministra dice que habrá más restricciones.", tipo="declaracion")

    attributed = claim(texto="La ministra dice que habrá más restricciones.", tipo="declaracion", atribuida_a="la ministra")
    assert attributed.atribuida_a == "la ministra"


def editorial_package(**changes) -> EditorialPackage:
    fields = dict(
        titulo="El Canal reduce los tránsitos por la sequía",
        brief="El Canal informa una reducción de tránsitos diarios.",
        enfoque_interes_publico="Efecto sobre el comercio y los costos logísticos.",
        preguntas=("¿Cuánto durará la restricción?", "¿Qué navieras se ven afectadas?", "¿Hay otras rutas?"),
        fuentes_y_verificaciones=("Confirmar la cifra con el comunicado del Canal.",),
        guion="El Canal de Panamá redujo los tránsitos diarios.",
        copy_digital="El Canal reduce los tránsitos por la sequía.",
        leyenda=None,
    )
    return EditorialPackage(**(fields | changes))


def test_brief_is_limited_to_250_words_and_copy_to_80():
    assert editorial_package(brief="palabra " * 250)
    with pytest.raises(ValueError, match="brief"):
        editorial_package(brief="palabra " * 251)
    assert editorial_package(copy_digital="palabra " * 80)
    with pytest.raises(ValueError, match="copy_digital"):
        editorial_package(copy_digital="palabra " * 81)


@pytest.mark.parametrize("count", [2, 4])
def test_the_package_has_exactly_three_research_questions(count):
    with pytest.raises(ValueError, match="preguntas"):
        editorial_package(preguntas=tuple(f"¿Pregunta {i}?" for i in range(count)))


def case_file(**changes) -> CaseFile:
    fields = dict(
        id_caso="CASO-001",
        id_grupo="G-001",
        alcance_texto="titular_descripcion",
        afirmaciones=(claim(),),
        borrador=editorial_package(),
        vacios=(),
        contradicciones=(),
        accion_recomendada="Confirmar la cifra con el Canal antes de publicar.",
    )
    return CaseFile(**(fields | changes))


def test_a_draft_based_only_on_headline_must_say_so():
    with pytest.raises(ValueError, match="leyenda"):
        case_file(alcance_texto="titular_metadatos", borrador=editorial_package(leyenda=None))

    assert case_file(alcance_texto="titular_metadatos", borrador=editorial_package(leyenda=HEADLINE_LEGEND))


def test_a_case_file_has_at_least_one_claim():
    with pytest.raises(ValueError, match="afirmaciones"):
        case_file(afirmaciones=())


def test_a_contradiction_shows_both_versions_with_their_source():
    one = ContradictionVersion(valor="2,1 %", alcance="anual 2025", id_evidencia="N-af71800f62ff")

    with pytest.raises(ValueError, match="versiones"):
        Contradiction(descripcion="Cifras distintas de inflación.", versiones=(one,))


def member(n: int, medium: str, provenance: str, published="2026-10-05T14:00:00Z", **changes) -> Member:
    fields = dict(
        id_noticia=f"N-{n:012d}",
        titulo=f"Titular {n}",
        url=f"https://ejemplo.test/{n}",
        medio=medium,
        procedencia=provenance,
        fecha_publicacion=published,
        alcance_texto="titular_metadatos",
        recirculada_en=None,
    )
    return Member(**(fields | changes))


LINK = ContextLink(
    id_evidencia="WB-PAN-NE.EXP.GNFS.ZS-2024",
    etiqueta="Exportaciones de bienes y servicios",
    pais="PAN",
    limitaciones="Serie anual: no es una medición actual.",
    razon="El Canal es la principal exportación de servicios.",
)


def group(id_grupo="G-001", members=None, score=None, **changes) -> Group:
    fields = dict(
        id_grupo=id_grupo,
        titulo="El Canal reduce los tránsitos",
        tema="logistica_canal",
        miembros=members or (member(1, "TVN", "Canal de Panamá"),),
        puntaje=score or Score.from_components(components(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), JUSTIFICATIONS),
        estado_evidencia="parcial",
        contexto=(LINK,),
        sin_contexto_motivo=None,
        id_caso=None,
    )
    return Group(**(fields | changes))


def test_a_replicated_wire_story_counts_as_one_provenance():
    # CU-03: three outlets republish the same agency item; a fourth reports independently.
    g = group(
        members=(
            member(1, "TVN", "EFE"),
            member(2, "Telemetro", "EFE"),
            member(3, "La Prensa", "EFE"),
            member(4, "Metro Libre", "Metro Libre"),
        )
    )

    assert (g.n_noticias, g.n_medios, g.n_procedencias) == (4, 4, 2)


def test_a_group_has_unique_members():
    with pytest.raises(ValueError, match="miembros"):
        group(members=(member(1, "TVN", "EFE"), member(1, "TVN", "EFE")))


def test_a_recirculated_story_keeps_its_original_date():
    with pytest.raises(ValueError, match="recirculada_en"):
        member(1, "TVN", "TVN", published="2026-10-05T14:00:00Z", recirculada_en="2025-11-02T10:00:00Z")

    old = member(1, "TVN", "TVN", published="2025-11-02T10:00:00Z", recirculada_en="2026-10-05T14:00:00Z")
    assert group(members=(old,)).miembros[0].fecha_publicacion == parse_utc("2025-11-02T10:00:00Z")


def test_without_official_context_the_group_says_why_not_forcing_a_link():
    with pytest.raises(ValueError, match="sin_contexto_motivo"):
        group(contexto=())

    assert group(contexto=(), sin_contexto_motivo="No hay indicador oficial pertinente.")
    with pytest.raises(ValueError, match="sin_contexto_motivo"):
        group(sin_contexto_motivo="Hay contexto y motivo a la vez.")


@pytest.mark.parametrize("field", ["limitaciones", "razon"])
def test_official_context_always_says_its_limitations_and_why_it_was_linked(field):
    with pytest.raises(ValueError, match=field):
        ContextLink(**(LINK.model_dump() | {field: " "}))


def test_official_context_cannot_point_to_a_news_item():
    with pytest.raises(ValueError, match="id_evidencia"):
        ContextLink(**(LINK.model_dump() | {"id_evidencia": "N-af71800f62ff"}))


def test_vocabularies_are_closed():
    for field, value in [("tema", "deportes"), ("estado_evidencia", "dudosa")]:
        with pytest.raises(ValueError, match=field):
            group(**{field: value})
    with pytest.raises(ValueError, match="alcance_texto"):
        case_file(alcance_texto="resumen")


def test_inbox_orders_by_score_then_urgency_then_id():
    top = Score.from_components(components(R=1, I=1, U=1, N=1, E=1), JUSTIFICATIONS)
    # Both reach P = 45 by different routes; the more urgent one goes first.
    urgent = Score.from_components(components(R=0.5, I=0.4, U=1.0, N=0.0, E=0.0), JUSTIFICATIONS)  # 15+10+20
    relaxed = Score.from_components(components(R=1.0, I=0.4, U=0.25, N=0.0, E=0.0), JUSTIFICATIONS)  # 30+10+5
    assert urgent.valor == relaxed.valor == 45.0

    ordered = sort_inbox(
        [group("G-003", score=relaxed), group("G-002", score=urgent), group("G-001", score=urgent), group("G-009", score=top)]
    )

    assert [g.id_grupo for g in ordered] == ["G-009", "G-001", "G-002", "G-003"]


def test_an_answer_with_evidence_cites_it():
    with pytest.raises(ValueError, match="citas"):
        Answer(id_consulta="Q-1", consulta="¿Cuántos buques cruzaron?", estado="respondida", respuesta="32 buques.")


def test_an_abstention_says_what_information_is_missing_and_answers_nothing():
    base = dict(id_consulta="Q-2", consulta="¿Cuál fue el PIB de 2027?", estado="abstencion")

    with pytest.raises(ValueError, match="faltante"):
        Answer(**base, motivo_abstencion="No hay datos.")
    with pytest.raises(ValueError, match="abstencion"):
        Answer(**base, respuesta="Será de 5 %.", motivo_abstencion="No hay datos.", faltante="Dato oficial de 2027.")

    assert Answer(**base, motivo_abstencion="No hay datos.", faltante="Dato oficial de 2027.")


def test_a_contradictory_answer_shows_both_versions():
    with pytest.raises(ValueError, match="versiones"):
        Answer(id_consulta="Q-3", consulta="¿Cuál es la inflación?", estado="contradiccion")


def review(id_caso="CASO-001", state="en_revision", at="2026-10-07T13:00:00Z", who="Ana", note=None) -> ReviewRecord:
    return ReviewRecord(id_caso=id_caso, estado=state, responsable=who, fecha=at, nota=note)


def test_a_review_beyond_new_names_the_responsible_person():
    with pytest.raises(ValueError, match="responsable"):
        review(state="aprobado_como_borrador", who="")
    with pytest.raises(ValueError, match="estado"):
        review(state="publicado")

    assert review(state="nuevo", who=None)


# ---------------------------------------------------------------------------
# Rules that span records (`verify`) and the review state derived from the history.
# ---------------------------------------------------------------------------

NEWS_ID = "N-af71800f62ff"

CONTEXT_EVIDENCE = Evidence(
    id_evidencia="WB-PAN-NE.EXP.GNFS.ZS-2024",
    tipo="indicador",
    titulo="Exportaciones de bienes y servicios (PAN, 2024)",
    url="https://api.worldbank.org/v2/country/PAN",
    fecha=None,
    campos={"indicador": "Exportaciones", "periodo": "2024", "valor": "44,36", "unidad": "% del PIB"},
)


def output_set(**changes) -> OutputSet:
    news = evidence()
    fields = dict(
        grupos=(
            group(
                members=(member(1, "TVN", "TVN", id_noticia=NEWS_ID),),
                estado_evidencia="suficiente_para_borrador",
                id_caso="CASO-001",
            ),
        ),
        evidencias={news.id_evidencia: news, CONTEXT_EVIDENCE.id_evidencia: CONTEXT_EVIDENCE},
        fichas=(case_file(),),
        consultas=(),
        revisiones=(),
    )
    return OutputSet(**(fields | changes))


def problems(output: OutputSet) -> str:
    with pytest.raises(ValueError) as caught:
        verify(output)
    return str(caught.value)


def test_a_coherent_output_set_verifies():
    verify(output_set())


def test_a_citation_that_does_not_resolve_is_reported():
    broken = case_file(afirmaciones=(claim(citas=(Citation(id_evidencia=NEWS_ID, campo="titulo", pasaje="no está"),)),))

    assert "literal" in problems(output_set(fichas=(broken,)))


def test_a_case_file_can_only_cite_evidence_of_its_own_group():
    stranger = Evidence(
        id_evidencia="N-0000000000aa",
        tipo="noticia",
        titulo="Otra",
        url="https://ejemplo.test/o",
        fecha=None,
        campos={"titulo": "Otra nota"},
    )
    cited = case_file(afirmaciones=(claim(citas=(Citation(id_evidencia=stranger.id_evidencia, campo="titulo", pasaje="Otra"),)),))
    evidences = output_set().evidencias | {stranger.id_evidencia: stranger}

    message = problems(output_set(evidencias=evidences, fichas=(cited,)))

    assert stranger.id_evidencia in message and "grupo" in message


def test_members_and_context_must_exist_as_evidence():
    without_context = {k: v for k, v in output_set().evidencias.items() if k != CONTEXT_EVIDENCE.id_evidencia}

    assert CONTEXT_EVIDENCE.id_evidencia in problems(output_set(evidencias=without_context))


@pytest.mark.parametrize("missing", ["periodo", "unidad", "valor"])
def test_official_context_evidence_carries_period_unit_and_value(missing):
    thin = CONTEXT_EVIDENCE.model_copy(update={"campos": {k: v for k, v in CONTEXT_EVIDENCE.campos.items() if k != missing}})
    evidences = output_set().evidencias | {thin.id_evidencia: thin}

    assert missing in problems(output_set(evidencias=evidences))


def test_a_case_file_and_its_group_point_at_each_other():
    detached = group(
        members=(member(1, "TVN", "TVN", id_noticia=NEWS_ID),),
        estado_evidencia="suficiente_para_borrador",
        id_caso=None,
    )

    assert "CASO-001" in problems(output_set(grupos=(detached,)))


def test_evidence_that_is_not_sufficient_must_say_what_is_missing():
    partial = group(members=(member(1, "TVN", "TVN", id_noticia=NEWS_ID),), estado_evidencia="parcial", id_caso="CASO-001")

    assert "vacios" in problems(output_set(grupos=(partial,)))
    verify(output_set(grupos=(partial,), fichas=(case_file(vacios=("Falta la cifra oficial.",)),)))


def insufficient_output(*records: ReviewRecord, draft=True) -> OutputSet:
    insufficient = group(
        members=(member(1, "TVN", "TVN", id_noticia=NEWS_ID),), estado_evidencia="insuficiente", id_caso="CASO-001"
    )
    filed = case_file(vacios=("Falta la cifra oficial.",), borrador=editorial_package() if draft else None)
    return output_set(grupos=(insufficient,), fichas=(filed,), revisiones=records)


APPROVAL = (review(state="en_revision", at="2026-10-07T12:00:00Z"), review(state="aprobado_como_borrador"))


def test_high_priority_with_insufficient_evidence_cannot_be_approved():
    assert "aprobado_como_borrador" in problems(insufficient_output(*APPROVAL))
    verify(insufficient_output(review(state="requiere_evidencia")))


def test_a_case_without_a_draft_cannot_be_approved():
    assert "borrador" in problems(output_set(fichas=(case_file(borrador=None),), revisiones=APPROVAL))


@pytest.mark.parametrize(
    ("history", "allowed"),
    [
        (["aprobado_como_borrador"], False),  # a new case must be reviewed first
        (["en_revision", "aprobado_como_borrador"], True),
        (["descartado", "aprobado_como_borrador"], False),  # a discarded case must be reopened first
        (["descartado", "en_revision", "aprobado_como_borrador"], True),
        (["en_revision", "en_revision"], False),  # not a change
    ],
)
def test_review_state_changes_follow_the_allowed_transitions(history, allowed):
    records = tuple(review(state=s, at=f"2026-10-07T1{i}:00:00Z") for i, s in enumerate(history))
    output = output_set(revisiones=records)

    if allowed:
        verify(output)
    else:
        assert "transición" in problems(output)


def test_the_current_review_state_is_the_latest_by_date_not_by_line_order():
    out_of_order = (
        review(state="aprobado_como_borrador", at="2026-10-07T14:00:00Z"),
        review(state="en_revision", at="2026-10-07T13:00:00Z"),
    )

    assert current_review_state(out_of_order, "CASO-001") == "aprobado_como_borrador"
    assert current_review_state((), "CASO-001") == "nuevo"
    verify(output_set(revisiones=out_of_order))


def test_a_review_of_an_unknown_case_is_reported():
    assert "CASO-099" in problems(output_set(revisiones=(review(id_caso="CASO-099"),)))
