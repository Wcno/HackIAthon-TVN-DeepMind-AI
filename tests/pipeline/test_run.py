import hashlib
import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from whoami import store
from whoami.pipeline.evidence import inec_evidence
from whoami.pipeline.run import PipelineInputError, build, group_by_similarity, load_vectors
from whoami.pipeline.topics_keywords import classify_keywords
from whoami.schemas import verify

CUTOFF = datetime(2026, 10, 7, 12, tzinfo=UTC)


def at(hours_ago: float) -> datetime:
    return CUTOFF - timedelta(hours=hours_ago)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def news(news_id, title, medium, published, description="", source="tvn", section="nacionales", origin="lastmod", modified=""):
    return {
        "id_noticia": news_id,
        "titulo": title,
        "url": f"https://example.test/{news_id}",
        "medio": medium,
        "fecha_publicacion": stamp(published),
        "origen_fecha_publicacion": origin,
        "alcance_texto": "titular_descripcion" if description else "titular_metadatos",
        "id_fuente": source,
        "seccion": section,
        "descripcion": description,
        "fecha_modificacion": modified,
    }


AGENCY_TITLE = "La inflación de agosto en Panamá fue de 1,2 % interanual"
ROWS = [
    news("N-a1", AGENCY_TITLE, "TVN", at(30), "Panamá, 5 oct (EFE).- Los precios al consumidor subieron 1,2 %."),
    news("N-a2", AGENCY_TITLE + " (Medio B)", "Medio B", at(29), "Panamá (EFE) - Los precios al consumidor subieron."),
    news("N-a3", AGENCY_TITLE.upper(), "Medio C", at(28), "EFE.- Los precios al consumidor subieron."),
    news(
        "N-o1",
        "ACP anuncia nueva licitación de remolcadores",
        "Autoridad del Canal de Panamá",
        at(6),
        "La Autoridad del Canal de Panamá abrió la licitación.",
        source="pancanal",
        section="Noticias",
    ),
    news(
        "N-r1",
        "Reactivan el turismo en Bocas del Toro",
        "TVN",
        datetime(2025, 12, 3, 10, tzinfo=UTC),
        origin="feed",
        modified=stamp(at(20)),
    ),
    news("N-u1", "Estrenan una película en los cines", "TVN", at(2), section="entretenimiento"),
]
VECTORS = np.array(
    [[1.0, 0.0, 0.0, 0.0], [0.99, 0.05, 0.0, 0.0], [0.98, 0.0, 0.05, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
)
OFFICIAL = {
    e.id_evidencia: e
    for e in [
        inec_evidence(
            {
                "serie_id": "ipc_var_interanual",
                "serie": "IPC, variación interanual",
                "periodo": "2026-08",
                "frecuencia": "mensual",
                "valor": "1.2",
                "unidad": "% interanual",
                "base": "2024=100",
                "fuente_url": "https://inec.test",
            }
        )
    ]
}


def build_fixture():
    return build(ROWS, VECTORS, classify_keywords, group_by_similarity, CUTOFF, official=OFFICIAL)


def group_with(output, news_id):
    return next(g for g in output.grupos if any(m.id_noticia == news_id for m in g.miembros))


def test_the_fixture_makes_four_groups_and_the_agency_story_is_one_provenance():
    output = build_fixture()

    assert len(output.grupos) == 4
    agency = group_with(output, "N-a1")
    assert agency.n_noticias == 3
    assert agency.n_medios == 3
    assert agency.n_procedencias == 1
    assert {m.procedencia for m in agency.miembros} == {"EFE"}


def test_every_component_is_between_zero_and_one_with_a_justification():
    for group in build_fixture().grupos:
        values = group.puntaje.componentes.model_dump().values()
        assert all(0 <= v <= 1 for v in values)
        assert set(group.puntaje.justificaciones) == {"R", "I", "U", "N", "E"}
        assert all(group.puntaje.justificaciones.values())


def test_the_recirculated_item_keeps_its_original_date_and_says_when_it_came_back():
    member = group_with(build_fixture(), "N-r1").miembros[0]

    assert member.fecha_publicacion == datetime(2025, 12, 3, 10, tzinfo=UTC)
    assert member.recirculada_en == at(20)
    assert member.recirculada_en > member.fecha_publicacion


def test_the_output_passes_verify_and_survives_a_write_and_load(tmp_path):
    output = build_fixture()

    verify(output)
    store.write(output, tmp_path / "data", tmp_path / "outputs")
    assert store.load(tmp_path / "data", tmp_path / "outputs").grupos == output.grupos


def test_the_inflation_story_links_the_inec_point_and_the_rest_say_why_not():
    output = build_fixture()

    agency = group_with(output, "N-a1")
    assert [c.id_evidencia for c in agency.contexto] == ["INEC-ipc_var_interanual-2026-08"]
    assert agency.sin_contexto_motivo is None
    unrelated = group_with(output, "N-u1")
    assert unrelated.contexto == ()
    assert unrelated.sin_contexto_motivo


def test_group_fields_come_from_the_members():
    output = build_fixture()
    agency = group_with(output, "N-a1")

    assert agency.id_grupo == "G-" + hashlib.sha1(b"N-a1,N-a2,N-a3").hexdigest()[:10]
    assert agency.tema == "economia"
    assert agency.id_caso is None
    assert agency.titulo in {m.titulo for m in agency.miembros}
    assert group_with(output, "N-u1").tema == "sin_tema"


def test_the_group_title_is_the_member_closest_to_the_centroid():
    vectors = VECTORS.copy()
    vectors[1] = [1.0, 0.0, 0.0, 0.0]
    vectors[0] = [0.9, 0.3, 0.0, 0.0]
    vectors[2] = [0.9, 0.0, 0.3, 0.0]

    output = build(ROWS, vectors, classify_keywords, group_by_similarity, CUTOFF, official=OFFICIAL)

    assert group_with(output, "N-a1").titulo == ROWS[1]["titulo"]


def voting(*votes):
    return lambda texts: [(topic, confidence, "x") for topic, confidence in votes]


def test_the_topic_is_the_majority_vote_of_the_members():
    classify = voting(("economia", 0.3), ("economia", 0.3), ("turismo", 0.9))

    output = build(ROWS[:3], VECTORS[:3], classify, group_by_similarity, CUTOFF, official=OFFICIAL)

    assert group_with(output, "N-a1").tema == "economia"


def test_a_tied_vote_goes_to_the_highest_summed_confidence():
    classify = voting(("economia", 0.2), ("turismo", 0.9))

    output = build(ROWS[:2], VECTORS[:2], classify, group_by_similarity, CUTOFF, official=OFFICIAL)

    assert group_with(output, "N-a1").tema == "turismo"


def test_the_evidence_set_has_every_news_item_and_every_official_record():
    output = build_fixture()

    assert set(output.evidencias) == {r["id_noticia"] for r in ROWS} | set(OFFICIAL)


def test_the_inbox_is_sorted_by_score():
    values = [g.puntaje.valor for g in build_fixture().grupos]

    assert values == sorted(values, reverse=True)


def test_the_groups_and_classifier_are_injected():
    seen = {}

    def classify(texts):
        seen["texts"] = texts
        return [("sin_tema", 0.0, "x")] * len(texts)

    def one_group(vectors, dates):
        seen["dates"] = dates
        return [list(range(len(dates)))]

    output = build(ROWS[:3], VECTORS[:3], classify, one_group, CUTOFF, official=OFFICIAL)

    assert len(output.grupos) == 1
    assert len(seen["texts"]) == 3
    assert all(d.tzinfo is not None for d in seen["dates"])


def test_novelty_compares_each_group_only_with_earlier_ones():
    vectors = np.array([[1.0, 0.0], [0.9, 0.1]])
    rows = [
        news("N-1", "Primera noticia", "TVN", at(100)),
        news("N-2", "Segunda noticia", "TVN", at(10)),
    ]

    output = build(rows, vectors, classify_keywords, lambda v, d: [[0], [1]], CUTOFF, official={})

    first, second = group_with(output, "N-1"), group_with(output, "N-2")
    assert first.puntaje.componentes.N == 1.0
    assert second.puntaje.componentes.N < 0.1


# ----------------------------------------------------------------------------------------------- grouping


def test_similar_vectors_within_the_window_form_one_group():
    vectors = np.array([[1.0, 0.0], [0.99, 0.05], [0.0, 1.0]])
    dates = [at(10), at(5), at(4)]

    assert group_by_similarity(vectors, dates) == [[0, 1], [2]]


def test_similar_vectors_more_than_72_hours_apart_stay_apart():
    vectors = np.array([[1.0, 0.0], [1.0, 0.0]])

    assert group_by_similarity(vectors, [at(100), at(10)]) == [[0], [1]]
    assert group_by_similarity(vectors, [at(76), at(3)]) == [[0], [1]]
    assert group_by_similarity(vectors, [at(75), at(4)]) == [[0, 1]]


def test_the_similarity_threshold_is_cosine_0_85():
    near = np.array([[1.0, 0.0], [np.cos(np.arccos(0.86)), np.sin(np.arccos(0.86))]])
    far = np.array([[1.0, 0.0], [np.cos(np.arccos(0.84)), np.sin(np.arccos(0.84))]])

    assert group_by_similarity(near, [at(2), at(1)]) == [[0, 1]]
    assert group_by_similarity(far, [at(2), at(1)]) == [[0], [1]]


def test_vector_length_does_not_matter():
    vectors = np.array([[10.0, 0.0], [0.1, 0.0]])

    assert group_by_similarity(vectors, [at(2), at(1)]) == [[0, 1]]


def test_grouping_is_single_link():
    a, b, c = (np.array([np.cos(t), np.sin(t)]) for t in (0.0, 0.4, 0.8))  # a-b and b-c ~0.92, a-c ~0.70

    assert group_by_similarity(np.array([a, b, c]), [at(3), at(2), at(1)]) == [[0, 1, 2]]


# ----------------------------------------------------------------------------------------------- vectors


def write_vectors(directory, ids, vectors):
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / "model.npy", vectors)
    (directory / "manifest.json").write_text(json.dumps({"ids": ids}), encoding="utf-8")
    return directory / "model.npy"


def test_vectors_load_when_their_ids_match_the_news(tmp_path):
    path = write_vectors(tmp_path, [r["id_noticia"] for r in ROWS], VECTORS)

    assert load_vectors(path, ROWS).shape == (6, 4)


def test_a_missing_vectors_file_is_a_clear_error(tmp_path):
    with pytest.raises(PipelineInputError, match="no existe"):
        load_vectors(tmp_path / "model.npy", ROWS)


def test_vectors_whose_ids_differ_from_the_news_are_rejected(tmp_path):
    ids = [r["id_noticia"] for r in ROWS]
    path = write_vectors(tmp_path, ids[::-1], VECTORS)

    with pytest.raises(PipelineInputError, match="ids"):
        load_vectors(path, ROWS)
