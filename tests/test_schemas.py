import math

import pytest

from whoami.schemas import (
    Afirmacion,
    Cita,
    Componentes,
    Contradiccion,
    Evidencia,
    Ficha,
    Grupo,
    Miembro,
    PaqueteEditorial,
    Puntaje,
    RegistroRevision,
    Respuesta,
    VersionContradictoria,
    VinculoContexto,
    calcular_puntaje,
    errores_de_citas,
    ordenar_bandeja,
    rango_de,
)


def componentes(R=0.0, I=0.0, U=0.0, N=0.0, E=0.0) -> Componentes:
    return Componentes(R=R, I=I, U=U, N=N, E=E)


# §4: P = 30R + 25I + 20U + 15N + 10E, each component in 0-1.
@pytest.mark.parametrize(
    ("valores", "esperado"),
    [
        (dict(R=1, I=1, U=1, N=1, E=1), 100.0),
        (dict(), 0.0),
        (dict(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), 71.5),  # 24 + 15 + 20 + 7.5 + 5
        (dict(R=0.25, N=1.0), 22.5),  # 7.5 + 15
    ],
)
def test_puntaje_follows_the_weighted_formula(valores, esperado):
    assert calcular_puntaje(componentes(**valores)) == esperado


@pytest.mark.parametrize("malo", [-0.01, 1.01, math.nan, math.inf])
def test_components_outside_zero_one_are_rejected(malo):
    with pytest.raises(ValueError, match="R"):
        componentes(R=malo)


# §4: bajo [0,40), medio [40,70), alto [70,100], sin solapamiento.
@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(0, "bajo"), (39.99, "bajo"), (40, "medio"), (69.99, "medio"), (70, "alto"), (100, "alto")],
)
def test_range_boundaries_do_not_overlap(valor, esperado):
    assert rango_de(valor) == esperado


@pytest.mark.parametrize("fuera", [-0.1, 100.01, math.nan])
def test_range_rejects_values_outside_zero_hundred(fuera):
    with pytest.raises(ValueError):
        rango_de(fuera)


JUSTIFICACIONES = {
    "R": "Afecta el tránsito por el Canal.",
    "I": "Alcance sectorial.",
    "U": "Publicado hace menos de 24 h.",
    "N": "Evento nuevo.",
    "E": "Dos procedencias distintas.",
}


def test_score_is_computed_from_components_never_supplied():
    puntaje = Puntaje.de(componentes(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), JUSTIFICACIONES)

    assert (puntaje.valor, puntaje.rango) == (71.5, "alto")
    assert puntaje.version_reglas == "1.0.0"


def test_a_score_whose_value_does_not_match_its_components_is_rejected():
    with pytest.raises(ValueError, match="valor"):
        Puntaje(
            componentes=componentes(R=1, I=1, U=1, N=1, E=1),
            valor=55.0,
            rango="medio",
            version_reglas="1.0.0",
            justificaciones=JUSTIFICACIONES,
        )


def test_a_score_whose_range_does_not_match_its_value_is_rejected():
    with pytest.raises(ValueError, match="rango"):
        Puntaje(
            componentes=componentes(R=1, I=1, U=1, N=1, E=1),
            valor=100.0,
            rango="bajo",
            version_reglas="1.0.0",
            justificaciones=JUSTIFICACIONES,
        )


@pytest.mark.parametrize("quitar", ["R", "E"])
def test_every_component_needs_a_justification(quitar):
    incompletas = {k: v for k, v in JUSTIFICACIONES.items() if k != quitar}

    with pytest.raises(ValueError, match=quitar):
        Puntaje.de(componentes(R=1), incompletas)


def evidencia(**cambios) -> Evidencia:
    datos = dict(
        id_evidencia="N-af71800f62ff",
        tipo="noticia",
        titulo="El Canal reduce los tránsitos diarios por la sequía",
        url="https://ejemplo.test/canal",
        fecha="2026-10-05T14:00:00Z",
        campos={"titulo": "El Canal reduce los tránsitos diarios por la sequía", "descripcion": "Pasan de 36 a 32 buques."},
    )
    return Evidencia(**(datos | cambios))


def test_evidence_id_prefix_must_match_its_type():
    with pytest.raises(ValueError, match="id_evidencia"):
        evidencia(id_evidencia="WB-PAN-NY.GDP.MKTP.KD.ZG-2023")


@pytest.mark.parametrize("fecha", ["2026-10-05", "2026-10-05T14:00:00-05:00", "ayer"])
def test_evidence_dates_must_be_iso_8601_utc(fecha):
    with pytest.raises(ValueError, match="fecha"):
        evidencia(fecha=fecha)


def test_a_citation_resolves_only_to_a_literal_passage_of_an_existing_field():
    registro = {"N-af71800f62ff": evidencia()}
    buena = Cita("N-af71800f62ff", "descripcion", "de 36 a 32 buques")

    assert errores_de_citas([buena], registro) == []


@pytest.mark.parametrize(
    ("cita", "fragmento"),
    [
        (Cita("N-000000000000", "titulo", "Canal"), "no existe"),
        (Cita("N-af71800f62ff", "cuerpo", "Canal"), "campo"),
        (Cita("N-af71800f62ff", "descripcion", "de 36 a 30 buques"), "literal"),
    ],
)
def test_citations_that_do_not_resolve_are_reported(cita, fragmento):
    errores = errores_de_citas([cita], {"N-af71800f62ff": evidencia()})

    assert len(errores) == 1 and fragmento in errores[0]


CITA = Cita("N-af71800f62ff", "titulo", "reduce los tránsitos")


def test_every_claim_needs_at_least_one_citation():
    with pytest.raises(ValueError, match="cita"):
        Afirmacion("A-1", "El Canal reduce los tránsitos.", "hecho", ())


def test_claim_type_must_be_one_of_the_four_the_challenge_distinguishes():
    with pytest.raises(ValueError, match="tipo"):
        Afirmacion("A-1", "El Canal reduce los tránsitos.", "rumor", (CITA,))


def test_a_statement_must_say_who_made_it():
    with pytest.raises(ValueError, match="atribuida_a"):
        Afirmacion("A-1", "La ministra dice que habrá más restricciones.", "declaracion", (CITA,))

    atribuida = Afirmacion("A-1", "La ministra dice que habrá más restricciones.", "declaracion", (CITA,), "la ministra")
    assert atribuida.atribuida_a == "la ministra"


LEYENDA = "basado únicamente en titular/metadatos"


def paquete(**cambios) -> PaqueteEditorial:
    datos = dict(
        titulo="El Canal reduce los tránsitos por la sequía",
        brief="El Canal informa una reducción de tránsitos diarios.",
        enfoque_interes_publico="Efecto sobre el comercio y los costos logísticos.",
        preguntas=("¿Cuánto durará la restricción?", "¿Qué navieras se ven afectadas?", "¿Hay otras rutas?"),
        fuentes_y_verificaciones=("Confirmar la cifra con el comunicado del Canal.",),
        guion="El Canal de Panamá redujo los tránsitos diarios.",
        copy_digital="El Canal reduce los tránsitos por la sequía.",
        leyenda=None,
    )
    return PaqueteEditorial(**(datos | cambios))


def test_brief_is_limited_to_250_words_and_copy_to_80():
    assert paquete(brief="palabra " * 250)
    with pytest.raises(ValueError, match="brief"):
        paquete(brief="palabra " * 251)
    assert paquete(copy_digital="palabra " * 80)
    with pytest.raises(ValueError, match="copy_digital"):
        paquete(copy_digital="palabra " * 81)


@pytest.mark.parametrize("cantidad", [2, 4])
def test_the_package_has_exactly_three_research_questions(cantidad):
    with pytest.raises(ValueError, match="preguntas"):
        paquete(preguntas=tuple(f"¿Pregunta {i}?" for i in range(cantidad)))


def ficha(**cambios) -> Ficha:
    datos = dict(
        id_caso="G-001",
        modalidad="editorial_tvn",
        id_grupo="G-001",
        titulo="El Canal reduce los tránsitos por la sequía",
        tema="logistica_canal",
        alcance_texto="titular_descripcion",
        ids_fuente=("N-af71800f62ff",),
        afirmaciones=(Afirmacion("A-1", "El Canal reduce los tránsitos.", "hecho", (CITA,)),),
        puntaje=Puntaje.de(componentes(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), JUSTIFICACIONES),
        estado_evidencia="suficiente_para_borrador",
        estado_revision="nuevo",
        borrador=paquete(),
        vacios=(),
        contradicciones=(),
        accion_recomendada="Confirmar la cifra con el Canal antes de publicar.",
    )
    return Ficha(**(datos | cambios))


def test_a_fiche_lists_every_source_it_cites():
    with pytest.raises(ValueError, match="ids_fuente"):
        ficha(ids_fuente=("N-otra00000000",))


def test_a_draft_based_only_on_headline_must_say_so():
    with pytest.raises(ValueError, match="leyenda"):
        ficha(alcance_texto="titular_metadatos", borrador=paquete(leyenda=None))

    assert ficha(alcance_texto="titular_metadatos", borrador=paquete(leyenda=LEYENDA))


def test_high_priority_with_insufficient_evidence_cannot_be_approved():
    with pytest.raises(ValueError, match="aprobado_como_borrador"):
        ficha(estado_evidencia="insuficiente", vacios=("Falta la cifra oficial.",), estado_revision="aprobado_como_borrador")

    assert ficha(estado_evidencia="insuficiente", vacios=("Falta la cifra oficial.",), estado_revision="requiere_evidencia")


@pytest.mark.parametrize("estado", ["insuficiente", "parcial"])
def test_missing_evidence_must_say_what_is_missing(estado):
    with pytest.raises(ValueError, match="vacios"):
        ficha(estado_evidencia=estado, vacios=())


def test_vocabularies_are_closed():
    for campo, valor in [("estado_evidencia", "dudosa"), ("estado_revision", "publicado"), ("tema", "deportes")]:
        with pytest.raises(ValueError, match=campo):
            ficha(**{campo: valor})


def test_a_contradiction_shows_both_versions_with_their_source():
    with pytest.raises(ValueError, match="versiones"):
        Contradiccion("Cifras distintas de inflación.", (VersionContradictoria("2,1 %", "anual 2025", "N-af71800f62ff"),))


def miembro(n: int, medio: str, procedencia: str, publicada="2026-10-05T14:00:00Z", **cambios) -> Miembro:
    datos = dict(
        id_noticia=f"N-{n:012d}",
        titulo=f"Titular {n}",
        url=f"https://ejemplo.test/{n}",
        medio=medio,
        procedencia=procedencia,
        fecha_publicacion=publicada,
        alcance_texto="titular_metadatos",
        recirculada_en=None,
    )
    return Miembro(**(datos | cambios))


VINCULO = VinculoContexto(
    id_evidencia="WB-PAN-NE.EXP.GNFS.ZS-2023",
    etiqueta="Exportaciones de bienes y servicios",
    pais="PAN",
    periodo="2023",
    valor=48.1,
    unidad="% del PIB",
    limitaciones="Serie anual: no es una medición actual.",
    razon="El Canal es la principal exportación de servicios.",
)


def grupo(id_grupo="G-001", miembros=None, puntaje=None, **cambios) -> Grupo:
    datos = dict(
        id_grupo=id_grupo,
        titulo="El Canal reduce los tránsitos",
        tema="logistica_canal",
        miembros=miembros or (miembro(1, "TVN", "Canal de Panamá"),),
        puntaje=puntaje or Puntaje.de(componentes(R=0.8, I=0.6, U=1.0, N=0.5, E=0.5), JUSTIFICACIONES),
        estado_evidencia="parcial",
        estado_revision="nuevo",
        contexto=(VINCULO,),
        sin_contexto_motivo=None,
        id_caso=None,
    )
    return Grupo(**(datos | cambios))


def test_a_replicated_wire_story_counts_as_one_provenance():
    # CU-03: three outlets republish the same agency item; a fourth reports independently.
    g = grupo(
        miembros=(
            miembro(1, "TVN", "EFE"),
            miembro(2, "Telemetro", "EFE"),
            miembro(3, "La Prensa", "EFE"),
            miembro(4, "Metro Libre", "Metro Libre"),
        )
    )

    assert (g.n_noticias, g.n_medios, g.n_procedencias) == (4, 4, 2)


def test_a_group_has_unique_members():
    with pytest.raises(ValueError, match="miembros"):
        grupo(miembros=(miembro(1, "TVN", "EFE"), miembro(1, "TVN", "EFE")))


def test_a_recirculated_story_keeps_its_original_date():
    with pytest.raises(ValueError, match="recirculada_en"):
        miembro(1, "TVN", "TVN", publicada="2026-10-05T14:00:00Z", recirculada_en="2025-11-02T10:00:00Z")

    vieja = miembro(1, "TVN", "TVN", publicada="2025-11-02T10:00:00Z", recirculada_en="2026-10-05T14:00:00Z")
    assert grupo(miembros=(vieja,)).miembros[0].fecha_publicacion == "2025-11-02T10:00:00Z"


def test_without_official_context_the_group_says_why_not_forcing_a_link():
    with pytest.raises(ValueError, match="sin_contexto_motivo"):
        grupo(contexto=())

    assert grupo(contexto=(), sin_contexto_motivo="No hay indicador oficial pertinente.")
    with pytest.raises(ValueError, match="sin_contexto_motivo"):
        grupo(sin_contexto_motivo="Hay contexto y motivo a la vez.")


def test_official_context_always_carries_period_unit_and_limitations():
    for campo in ("periodo", "unidad", "limitaciones"):
        with pytest.raises(ValueError, match=campo):
            VinculoContexto(**({**VINCULO.__dict__, campo: " "}))


def test_official_context_cannot_point_to_a_news_item():
    with pytest.raises(ValueError, match="id_evidencia"):
        VinculoContexto(**({**VINCULO.__dict__, "id_evidencia": "N-af71800f62ff"}))


def test_inbox_orders_by_score_then_urgency_then_id():
    alto = Puntaje.de(componentes(R=1, I=1, U=1, N=1, E=1), JUSTIFICACIONES)
    # Both reach P = 45 by different routes; the more urgent one goes first.
    urgente = Puntaje.de(componentes(R=0.5, I=0.4, U=1.0, N=0.0, E=0.0), JUSTIFICACIONES)  # 15+10+20 = 45
    pausado = Puntaje.de(componentes(R=1.0, I=0.4, U=0.25, N=0.0, E=0.0), JUSTIFICACIONES)  # 30+10+5 = 45
    assert urgente.valor == pausado.valor == 45.0

    ordenados = ordenar_bandeja(
        [
            grupo("G-003", puntaje=pausado),
            grupo("G-002", puntaje=urgente),
            grupo("G-001", puntaje=urgente),
            grupo("G-009", puntaje=alto),
        ]
    )

    assert [g.id_grupo for g in ordenados] == ["G-009", "G-001", "G-002", "G-003"]


def test_an_answer_with_evidence_cites_it():
    with pytest.raises(ValueError, match="citas"):
        Respuesta("Q-1", "¿Cuántos buques cruzaron?", "respondida", respuesta="32 buques.")


def test_an_abstention_says_what_information_is_missing_and_answers_nothing():
    with pytest.raises(ValueError, match="faltante"):
        Respuesta("Q-2", "¿Cuál fue el PIB de 2027?", "abstencion", motivo_abstencion="No hay datos.")
    with pytest.raises(ValueError, match="abstencion"):
        Respuesta(
            "Q-2", "¿Cuál fue el PIB de 2027?", "abstencion",
            respuesta="Será de 5 %.", motivo_abstencion="No hay datos.", faltante="Dato oficial de 2027.",
        )

    assert Respuesta(
        "Q-2", "¿Cuál fue el PIB de 2027?", "abstencion",
        motivo_abstencion="No hay datos.", faltante="Dato oficial de 2027.",
    )


def test_a_contradictory_answer_shows_both_versions():
    with pytest.raises(ValueError, match="versiones"):
        Respuesta("Q-3", "¿Cuál es la inflación?", "contradiccion")


def test_a_review_beyond_new_names_the_responsible_person():
    with pytest.raises(ValueError, match="responsable"):
        RegistroRevision("G-001", "aprobado_como_borrador", "", "2026-10-07T15:00:00Z", None)
    with pytest.raises(ValueError, match="estado"):
        RegistroRevision("G-001", "publicado", "Ana", "2026-10-07T15:00:00Z", None)

    assert RegistroRevision("G-001", "nuevo", None, "2026-10-07T15:00:00Z", None)
