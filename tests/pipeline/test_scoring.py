import json
from datetime import UTC, datetime, timedelta

import pytest

from whoami.contracts import PROCESSED
from whoami.pipeline.scoring import (
    OFFICIAL_SOURCES,
    evidence_component,
    evidence_state,
    impact,
    novelty,
    relevance,
    score_group,
    urgency,
)
from whoami.schemas import Member

CUTOFF = datetime(2026, 10, 7, 12, tzinfo=UTC)


def row(title="Titular", description="", section="nacionales", source="tvn", medium="TVN") -> dict:
    return {"titulo": title, "descripcion": description, "seccion": section, "id_fuente": source, "medio": medium}


def test_official_sources_match_the_ones_declared_in_fuentes_json():
    declared = json.loads((PROCESSED / "fuentes.json").read_text(encoding="utf-8"))["fuentes"]

    assert OFFICIAL_SOURCES == {s["id_fuente"] for s in declared if s["tipo"] == "oficial"}


# ----------------------------------------------------------------------------------------------- R


def test_relevance_is_full_for_a_topic_about_panama():
    value, why = relevance("economia", [row("El MEF presenta el presupuesto", section="mundo")])

    assert value == 1.0
    assert "Panamá" in why


def test_relevance_is_zero_panama_part_for_world_news_without_mention():
    value, _ = relevance("economia", [row("Sube el petróleo", section="mundo")])

    assert value == pytest.approx(0.6)


def test_relevance_is_half_panama_when_the_link_to_panama_is_unknown():
    value, _ = relevance("economia", [row("Sube el petróleo", section="tvmax")])

    assert value == pytest.approx(0.6 + 0.4 * 0.5)


def test_relevance_without_topic_only_counts_panama():
    value, _ = relevance("sin_tema", [row("Gran concierto en Panamá", section="mundo")])

    assert value == pytest.approx(0.4)


def test_an_official_source_or_a_national_section_is_about_panama():
    assert relevance("economia", [row(section="tvmax", source="mici")])[0] == 1.0
    assert relevance("economia", [row(section="economia")])[0] == 1.0


def test_acronyms_are_case_sensitive_and_provinces_are_not_accent_sensitive():
    assert relevance("economia", [row("Anuncio de la ACP", section="mundo")])[0] == 1.0
    assert relevance("economia", [row("Lluvias en CHIRIQUI", section="mundo")])[0] == 1.0
    assert relevance("economia", [row("Un acp cualquiera", section="mundo")])[0] == pytest.approx(0.6)


# ----------------------------------------------------------------------------------------------- I


def test_impact_is_the_topic_base_without_extras():
    assert impact("turismo", "Festival de música", has_context=False)[0] == pytest.approx(0.4)
    assert impact("sin_tema", "Festival de música", has_context=False)[0] == pytest.approx(0.1)


@pytest.mark.parametrize(
    "text",
    ["Una inversión de $5 millones", "Sube 3,5%", "Cae 2 por ciento", "Medidas a nivel nacional", "En todo el país", "Afectadas 120 viviendas", "Hay 300 familias damnificadas"],
)
def test_a_scale_signal_adds_two_tenths(text):
    value, why = impact("economia", text, has_context=False)

    assert value == pytest.approx(0.8)
    assert "escala" in why


def test_official_context_adds_two_tenths_and_the_total_is_capped_at_one():
    assert impact("economia", "Sin cifras", has_context=True)[0] == pytest.approx(0.8)
    assert impact("logistica_canal", "Pierde $20 millones a nivel nacional", has_context=True)[0] == 1.0


def test_the_asamblea_nacional_is_not_a_scale_signal():
    assert impact("regulacion", "La Asamblea Nacional discute el proyecto", has_context=False)[0] == pytest.approx(0.5)


# ----------------------------------------------------------------------------------------------- U


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(hours=3), 1.0),
        (timedelta(hours=30), 0.8),
        (timedelta(hours=60), 0.6),
        (timedelta(days=5), 0.4),
        (timedelta(days=10), 0.2),
        (timedelta(days=40), 0.1),
    ],
)
def test_urgency_decays_with_the_age_of_the_newest_original_date(age, expected):
    assert urgency(CUTOFF - age, "Sin más", CUTOFF)[0] == pytest.approx(expected)


def test_an_active_alert_or_a_future_date_adds_two_tenths_up_to_one():
    old = CUTOFF - timedelta(days=5)

    assert urgency(old, "Emiten aviso de lluvias", CUTOFF)[0] == pytest.approx(0.6)
    assert urgency(old, "Rige a partir del lunes", CUTOFF)[0] == pytest.approx(0.6)
    assert urgency(old, "Cierre el 12 de octubre", CUTOFF)[0] == pytest.approx(0.6)
    assert urgency(CUTOFF - timedelta(hours=1), "Alerta roja", CUTOFF)[0] == 1.0


def test_a_past_date_is_not_a_future_date():
    assert urgency(CUTOFF - timedelta(days=5), "Ocurrió el 2 de octubre", CUTOFF)[0] == pytest.approx(0.4)
    assert urgency(CUTOFF - timedelta(days=5), "Desde el 5 de enero de 2026", CUTOFF)[0] == pytest.approx(0.4)


# ----------------------------------------------------------------------------------------------- N


@pytest.mark.parametrize(("similarity", "expected"), [(0.2, 1.0), (0.5, 1.0), (0.7, 0.5), (0.9, 0.0), (0.99, 0.0)])
def test_novelty_maps_similarity_linearly_between_half_and_nine_tenths(similarity, expected):
    assert novelty(similarity, recirculated=False)[0] == pytest.approx(expected)


def test_a_recirculated_group_is_not_novel():
    value, why = novelty(0.1, recirculated=True)

    assert value == pytest.approx(0.1)
    assert "republic" in why.lower()


# ----------------------------------------------------------------------------------------------- E


def test_evidence_counts_provenances_not_news_items_up_to_three():
    one, _ = evidence_component(1, has_primary=False, has_text=False)
    three, _ = evidence_component(3, has_primary=False, has_text=False)
    ten, _ = evidence_component(10, has_primary=False, has_text=False)

    assert one == pytest.approx(0.4 / 3, abs=1e-4)
    assert three == pytest.approx(0.4)
    assert ten == three


def test_evidence_adds_primary_source_and_text():
    assert evidence_component(3, has_primary=True, has_text=True)[0] == pytest.approx(1.0)
    assert evidence_component(1, has_primary=True, has_text=False)[0] == pytest.approx(0.4 / 3 + 0.3, abs=1e-4)


def test_evidence_state_is_sufficient_with_an_official_source_with_text():
    assert evidence_state([row("t", "con texto", source="mici")], 1, has_context=False) == "suficiente_para_borrador"


def test_evidence_state_is_sufficient_with_two_provenances_and_some_text():
    rows = [row("a", "con texto"), row("b")]

    assert evidence_state(rows, 2, has_context=False) == "suficiente_para_borrador"


def test_evidence_state_is_partial_with_one_signal_only():
    assert evidence_state([row("a", "con texto")], 1, has_context=False) == "parcial"
    assert evidence_state([row("a")], 1, has_context=True) == "parcial"
    assert evidence_state([row("a"), row("b")], 2, has_context=False) == "parcial"


def test_evidence_state_is_insufficient_with_a_single_headline():
    assert evidence_state([row("a")], 1, has_context=False) == "insuficiente"


def test_an_official_source_without_text_and_nothing_else_is_insufficient():
    assert evidence_state([row("a", source="mici")], 1, has_context=False) == "insuficiente"


# ----------------------------------------------------------------------------------------------- Score


def member(news_id, published, recirculated=None, provenance="TVN") -> Member:
    return Member(
        id_noticia=news_id,
        titulo="Titular",
        url="https://example.test",
        medio="TVN",
        procedencia=provenance,
        fecha_publicacion=published,
        alcance_texto="titular_metadatos",
        recirculada_en=recirculated,
    )


def test_score_group_builds_the_score_with_a_justification_per_component():
    rows = [row("El Canal de Panamá limita tránsitos", "Pierde $5 millones", source="pancanal")]
    members = [member("N-1", CUTOFF - timedelta(hours=5), provenance="Autoridad del Canal de Panamá")]

    score = score_group(rows, members, "logistica_canal", has_context=False, max_similarity=0.3, fecha_corte=CUTOFF)

    assert score.componentes.R == pytest.approx(1.0)
    assert score.componentes.I == pytest.approx(0.8)
    assert score.componentes.U == 1.0
    assert score.componentes.N == 1.0
    assert score.componentes.E == pytest.approx(0.4 / 3 + 0.3 + 0.3, abs=1e-4)
    assert set(score.justificaciones) == {"R", "I", "U", "N", "E"}
    assert all(score.justificaciones.values())


def test_duplicating_news_does_not_raise_the_score():
    base = [member("N-1", CUTOFF - timedelta(hours=5))]
    duplicated = base + [member(f"N-{i}", CUTOFF - timedelta(hours=5)) for i in range(2, 8)]

    one = score_group([row()], base, "economia", False, 0.3, CUTOFF)
    many = score_group([row() for _ in duplicated], duplicated, "economia", False, 0.3, CUTOFF)

    assert one.valor == many.valor


def test_a_group_where_every_member_came_back_is_recirculated_and_uses_the_original_date():
    old = CUTOFF - timedelta(days=60)
    members = [member("N-1", old, recirculated=CUTOFF - timedelta(hours=2))]

    score = score_group([row()], members, "economia", False, 0.1, CUTOFF)

    assert score.componentes.N == pytest.approx(0.1)
    assert score.componentes.U == pytest.approx(0.1)


def test_one_fresh_member_keeps_the_group_novel():
    old = CUTOFF - timedelta(days=60)
    members = [member("N-1", old, recirculated=CUTOFF - timedelta(hours=2)), member("N-2", CUTOFF - timedelta(hours=2))]

    score = score_group([row(), row()], members, "economia", False, 0.1, CUTOFF)

    assert score.componentes.N == 1.0
    assert score.componentes.U == 1.0


def test_relevance_names_the_method_that_assigned_the_topic():
    _, with_topic = relevance("economia", [row("El MEF presenta el presupuesto")], "llm")
    _, without_topic = relevance("sin_tema", [row("Gran concierto en Panamá")], "embeddings")
    _, unknown = relevance("economia", [row("El MEF presenta el presupuesto")], "palabras_clave_v1")

    assert "Economía, por modelo de lenguaje" in with_topic
    assert "No tiene tema editorial (por embeddings)" in without_topic
    assert "por " not in unknown.split(";")[0]
