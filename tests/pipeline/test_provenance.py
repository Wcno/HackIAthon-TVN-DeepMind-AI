from datetime import UTC, datetime

import pytest

from whoami.pipeline.provenance import AGENCIES, merge_provenances, near_identical, provenance
from whoami.schemas import Member


def row(title="Titular", description="", medio="TVN") -> dict:
    return {"titulo": title, "descripcion": description, "medio": medio}


def test_the_known_agencies():
    assert AGENCIES == ("EFE", "AFP", "Reuters", "AP", "Europa Press", "ANSA", "DPA", "Xinhua")


@pytest.mark.parametrize(
    ("title", "description", "agency"),
    [
        ("Panamá, 5 oct (EFE).- El Canal limita tránsitos", "", "EFE"),
        ("EFE.- Sube el precio", "", "EFE"),
        ("Titular", "Según la Agencia EFE, el hecho ocurrió ayer.", "EFE"),
        ("Titular", "Panamá (AFP) - Algo pasó", "AFP"),
        ("Titular", "Reuters informó que el barco llegó", "Reuters"),
        ("Titular", "(AP) Dos barcos chocaron", "AP"),
        ("Titular (Europa Press)", "", "Europa Press"),
        ("Titular", "Roma (ANSA) - Cumbre", "ANSA"),
        ("Titular", "Berlín (DPA) - Cumbre", "DPA"),
        ("Titular", "Pekín (Xinhua) - Cumbre", "Xinhua"),
    ],
)
def test_an_agency_is_detected_in_title_or_description(title, description, agency):
    assert provenance(row(title, description, medio="Medio X")) == agency


@pytest.mark.parametrize("text", ["La lluvia cayó sobre el capó", "Un mapa del tesoro", "Manifestación con pancartas AP2"])
def test_short_agency_names_do_not_match_inside_words(text):
    assert provenance(row(text, "", medio="Medio X")) == "Medio X"


def test_lowercase_short_names_are_not_agencies():
    assert provenance(row("el ap y la efe no son agencias", "", medio="Medio X")) == "Medio X"


def test_without_an_agency_the_provenance_is_the_outlet():
    assert provenance(row(medio="Autoridad del Canal de Panamá")) == "Autoridad del Canal de Panamá"


def test_near_identical_ignores_case_accents_punctuation_and_outlet_suffix():
    a = "El Canal de Panamá limitará los tránsitos diarios por la sequía (Medio A)"
    b = "EL CANAL DE PANAMA LIMITARA LOS TRANSITOS DIARIOS POR LA SEQUIA!"
    assert near_identical(a, b)


def test_near_identical_ignores_spanish_stopwords():
    assert near_identical("Canal limita los tránsitos de la semana", "Canal limita tránsitos semana")


def test_different_stories_are_not_near_identical():
    assert not near_identical("El Canal limita los tránsitos diarios", "Detienen a exejecutivo bancario por el caso Pandora")


def test_a_one_word_difference_in_a_long_headline_is_still_near_identical():
    assert near_identical(
        "Canal de Panamá limitará tránsitos diarios sequía lago Gatún octubre",
        "Canal de Panamá limitará tránsitos diarios sequía lago Gatún",
    )


def test_empty_texts_are_not_near_identical():
    assert not near_identical("", "")


def member(news_id, medium, provenance_, title, day) -> Member:
    return Member(
        id_noticia=news_id,
        titulo=title,
        url=f"https://example.test/{news_id}",
        medio=medium,
        procedencia=provenance_,
        fecha_publicacion=datetime(2026, 10, day, 12, tzinfo=UTC),
        alcance_texto="titular_metadatos",
        recirculada_en=None,
    )


RELEASE = "El Canal de Panamá limitará a 32 los tránsitos diarios por la sequía"


def test_an_outlet_copying_a_release_takes_the_origin_of_the_earlier_member():
    members = [
        member("N-1", "Autoridad del Canal de Panamá", "Autoridad del Canal de Panamá", RELEASE, 4),
        member("N-2", "TVN", "TVN", RELEASE + " (TVN)", 5),
    ]

    merged = merge_provenances(members)

    assert [m.procedencia for m in merged] == ["Autoridad del Canal de Panamá"] * 2
    assert members[1].procedencia == "TVN"


def test_merging_keeps_the_original_order_and_never_looks_at_later_members():
    members = [
        member("N-2", "TVN", "TVN", RELEASE, 5),
        member("N-1", "Autoridad del Canal de Panamá", "Autoridad del Canal de Panamá", RELEASE, 4),
    ]

    merged = merge_provenances(members)

    assert [m.id_noticia for m in merged] == ["N-2", "N-1"]
    assert [m.procedencia for m in merged] == ["Autoridad del Canal de Panamá"] * 2


def test_the_same_outlet_republishing_keeps_its_own_provenance():
    members = [member("N-1", "TVN", "TVN", RELEASE, 4), member("N-2", "TVN", "TVN", RELEASE, 5)]

    assert [m.procedencia for m in merge_provenances(members)] == ["TVN", "TVN"]


def test_different_stories_keep_their_provenance():
    members = [
        member("N-1", "Medio A", "Medio A", RELEASE, 4),
        member("N-2", "Medio B", "Medio B", "Detienen a exejecutivo bancario por el caso Pandora", 5),
    ]

    assert [m.procedencia for m in merge_provenances(members)] == ["Medio A", "Medio B"]
