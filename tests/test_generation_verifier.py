from decimal import Decimal

import pytest


@pytest.mark.parametrize("text, expected", [("-0,5 %", "-0.5"), ("+0,5 %", "0.5"),
                                          ("−32 millones", "-32000000"), ("menos cinco", "-5")])
def test_numeric_grounding_preserves_the_sign(text, expected):
    from decimal import Decimal
    from whoami.generation.verifier import normalize_numbers
    assert normalize_numbers(text) == [Decimal(expected)]

from whoami.generation.verifier import (
    normalize_numbers,
    repair_passage,
    verify_case_file,
    verify_claim,
    verify_claims,
)
from whoami.schemas import CaseFile, Citation, Claim, Evidence

D = Decimal


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.500", [D(1500)]),
        ("1,500", [D(1500)]),
        ("1500", [D(1500)]),
        ("1,1", [D("1.1")]),
        ("1.1", [D("1.1")]),
        ("2,3 %", [D("2.3")]),
        ("15%", [D(15)]),
        ("15 por ciento", [D(15)]),
        ("B/.3,000", [D(3000)]),
        ("$32 millones", [D(32_000_000)]),
        ("1,5 millones", [D(1_500_000)]),
        ("32 mil millones", [D(32_000_000_000)]),
        ("mil quinientos", [D(1500)]),
        ("dos mil", [D(2000)]),
        ("treinta y tres", [D(33)]),
        ("un millón", [D(1_000_000)]),
        ("dos millones quinientos mil", [D(2_500_000)]),
        ("veintiuno", [D(21)]),
        ("doscientos cincuenta", [D(250)]),
        ("en 2024", [D(2024)]),
        ("1.234.567", [D(1_234_567)]),
        ("1.234,56", [D("1234.56")]),
        ("1,234.56", [D("1234.56")]),
        ("0,500", [D("0.5")]),
        ("44,36 % del PIB", [D("44.36")]),
        ("el 12 de octubre o el 15 de octubre", [D(12), D(15)]),
        ("tres medios, cuatro agencias", [D(3), D(4)]),
        ("una reducción de tránsitos", []),
        ("sin cifras", []),
        ("Millones en juego y tensión", []),
        ("Miles de familias y cientos de empresas", []),
        ("Miles de millones en juego", []),
        ("mil", [D(1000)]),
        ("94 millones", [D(94_000_000)]),
        ("mil millones", [D(1_000_000_000)]),
    ],
)
def test_normalize_numbers(text, expected):
    assert normalize_numbers(text) == expected


def test_normalize_numbers_is_blind_to_the_percent_sign_and_the_trailing_period():
    assert normalize_numbers("subió 2,3 %.") == normalize_numbers("subió 2,3 por ciento")


FIELD = "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios a partir del 12 de octubre."


@pytest.mark.parametrize(
    ("passage", "expected"),
    [
        ("limitará a 32 los tránsitos diarios", "limitará a 32 los tránsitos diarios"),
        ("LIMITARÁ A 32 LOS TRÁNSITOS DIARIOS", "limitará a 32 los tránsitos diarios"),
        ("limitara a 32 los transitos diarios", "limitará a 32 los tránsitos diarios"),
        ("limitará a 33 los tránsitos diarios", "limitará a 32 los tránsitos diarios"),
        ("limitará a 32 los tránsitos diarios,", "limitará a 32 los tránsitos diarios"),
        ("limitara a 32 los tránsitos diario", "limitará a 32 los tránsitos diario"),
        ("reducirá a 10 las rutas marítimas del Pacífico", None),
        ("nada que ver con el campo", None),
    ],
)
def test_repair_passage(passage, expected):
    assert repair_passage(passage, FIELD) == expected


def test_repair_passage_maps_neutralized_angle_brackets_back():
    field = "usa <b>negrita</b> aquí"
    assert repair_passage("usa ‹b›negrita‹/b›", field) == "usa <b>negrita</b>"


def news(id_: str, **fields: str) -> Evidence:
    return Evidence(id_evidencia=id_, tipo="noticia", titulo="t", url="https://x.invalid", fecha=None, campos=fields)


def indicator(period: str = "2024", value: str = "44,36") -> Evidence:
    return Evidence(
        id_evidencia=f"WB-PAN-X-{period}",
        tipo="indicador",
        titulo="Indicador",
        url="https://x.invalid",
        fecha=None,
        campos={"indicador": "Exportaciones", "periodo": period, "valor": value, "unidad": "% del PIB"},
    )


EVIDENCES = {e.id_evidencia: e for e in (news("N-1", titulo="Canal", descripcion=FIELD), indicator())}


def claim(text, passage="limitará a 32 los tránsitos diarios", *, evidence="N-1", field="descripcion", **extra):
    return Claim(
        id_afirmacion=extra.pop("id_afirmacion", "A-1"),
        texto=text,
        tipo=extra.pop("tipo", "hecho"),
        citas=(Citation(id_evidencia=evidence, campo=field, pasaje=passage),),
        **extra,
    )


def test_a_grounded_claim_has_no_issues():
    assert verify_claim(claim("El Canal limitará a 32 los tránsitos diarios desde el 12 de octubre."), EVIDENCES) == []


def test_literal_source_text_cannot_authorize_an_internal_canary_in_a_claim():
    from whoami.generation.prompting import CANARY
    source = news("N-1", descripcion=CANARY)
    assert verify_claim(claim(CANARY, passage=CANARY), {"N-1": source})


@pytest.mark.parametrize("sign", ["+", "", "−"])
def test_claims_reject_opposite_signs_against_negative_official_evidence(sign):
    source = indicator(period="2024", value="-0,5")
    statement = claim(f"El indicador fue {sign}0,5 % en 2024.", evidence=source.id_evidencia, field="valor", passage="-0,5")
    issues = verify_claim(statement, {source.id_evidencia: source})
    assert bool(issues) == (sign != "−")


def test_a_claim_with_a_missing_evidence_is_reported():
    assert verify_claim(claim("Texto.", evidence="N-9"), EVIDENCES) == ["N-9: la evidencia no existe"]


def test_a_claim_with_a_non_literal_passage_is_reported():
    issues = verify_claim(claim("Texto.", passage="reducirá a 10 las rutas marítimas del Pacífico"), EVIDENCES)
    assert len(issues) == 1 and "no es literal" in issues[0]


def test_a_claim_with_an_unsupported_number_is_reported():
    issues = verify_claim(claim("El Canal limitará a 40 los tránsitos diarios."), EVIDENCES)
    assert issues == ["cifra no respaldada: 40"]


def test_a_number_written_in_words_is_compared_with_the_digits_of_the_source():
    assert verify_claim(claim("El Canal limitará a treinta y dos los tránsitos."), EVIDENCES) == []


def test_numbers_may_come_from_the_full_cited_field():
    assert verify_claim(claim("Será desde el 12 de octubre."), EVIDENCES) == []


def test_a_claim_citing_official_figures_must_state_the_period():
    cited = {"evidence": "WB-PAN-X-2024", "field": "valor", "passage": "44,36"}
    assert verify_claim(claim("Fueron 44,36 % del PIB en 2024.", **cited), EVIDENCES) == []
    assert verify_claim(claim("Fueron 44,36 % del PIB.", **cited), EVIDENCES) == ["cifra oficial sin período"]


def test_a_claim_citing_official_figures_is_not_presented_as_current():
    cited = {"evidence": "WB-PAN-X-2024", "field": "valor", "passage": "44,36"}
    issues = verify_claim(claim("Hoy son 44,36 % del PIB (2024).", **cited), EVIDENCES)
    assert issues == ["cifra oficial presentada como actual"]


def test_an_accusation_cannot_be_presented_as_fact():
    text = "El gerente robó fondos."
    assert verify_claim(claim(text, passage="Canal"), EVIDENCES) == ["acusación presentada como hecho"]
    attributed = claim(text, passage="Canal", tipo="declaracion", atribuida_a="la fiscalía")
    assert verify_claim(attributed, EVIDENCES) == []


def test_verify_claim_repairs_a_citation_that_differs_only_in_accents():
    assert verify_claim(claim("El Canal limitará los tránsitos.", passage="limitara a 32 los transitos"), EVIDENCES) == []


def test_the_report_keeps_repaired_claims_and_counts_repairs():
    good = claim("El Canal limitará los tránsitos.", passage="LIMITARÁ A 32 LOS TRÁNSITOS DIARIOS")
    bad = claim("Texto.", passage="no está en la fuente de ninguna manera", id_afirmacion="A-2")
    report = verify_claims([good, bad], EVIDENCES)
    assert [c.id_afirmacion for c in report.valid_claims] == ["A-1"]
    assert report.valid_claims[0].citas[0].pasaje == "limitará a 32 los tránsitos diarios"
    assert list(report.issues) == ["A-2"]
    assert [(r.id_afirmacion, r.original.pasaje) for r in report.repaired] == [("A-1", "LIMITARÁ A 32 LOS TRÁNSITOS DIARIOS")]


def test_verify_case_file_reports_per_claim_issues():
    case_file = CaseFile(
        id_caso="CASO-1",
        id_grupo="G-1",
        alcance_texto="titular_descripcion",
        afirmaciones=(claim("El Canal limitará los tránsitos."),),
        borrador=None,
        vacios=(),
        contradicciones=(),
        accion_recomendada="Revisar.",
    )
    report = verify_case_file(case_file, EVIDENCES)
    assert len(report.valid_claims) == 1 and not report.issues and not report.repaired


def test_a_date_from_the_cited_record_publication_date_is_supported():
    from whoami.generation.verifier import unsupported_numbers
    from whoami.schemas import Citation, Evidence

    evidence = Evidence(
        id_evidencia="N-18aa523e6849",
        tipo="noticia",
        titulo="Sismos en Chiriquí de magnitud 5.4",
        url="https://example.invalid/sismo",
        fecha=None,
        campos={"titulo": "Sismos en Chiriquí de magnitud 5.4", "fecha_publicacion": "2026-09-12T19:56:08Z"},
    )
    citation = Citation(id_evidencia="N-18aa523e6849", campo="titulo", pasaje="Sismos en Chiriquí de magnitud 5.4")
    text = "El 12 de septiembre de 2026 se reportó un sismo de magnitud 5.4 en Chiriquí."
    assert unsupported_numbers(text, [citation], {evidence.id_evidencia: evidence}) == []
    assert unsupported_numbers("Hubo 7 heridos.", [citation], {evidence.id_evidencia: evidence}) == [7]
