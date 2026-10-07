import pytest

from whoami.contracts import CLAIM_TYPES, HEADLINE_ONLY_LEGEND
from whoami.generation.jsonschemas import (
    answer_schema,
    case_file_schema,
    citation_schema,
    claims_schema,
    contradiction_pair_schema,
    entailment_schema,
    gate_schema,
    package_schema,
    response_format,
    single_shot_schema,
    to_answer,
    to_claims,
    to_package,
)
from whoami.schemas import Citation

IDS = ["N-aaa", "WB-PAN-X-2024"]


def all_schemas() -> dict[str, dict]:
    return {
        "citation": citation_schema(IDS),
        "case_file": case_file_schema(IDS),
        "single_shot": single_shot_schema(IDS),
        "package": package_schema(IDS),
        "claims": claims_schema(IDS),
        "answer": answer_schema(IDS),
        "entailment": entailment_schema(),
        "gate": gate_schema(),
        "contradiction_pair": contradiction_pair_schema(),
    }


def strict_shape_errors(schema: dict, path: str = "$") -> list[str]:
    """Recursive check of the strict, Gemini-compatible subset of JSON Schema."""
    errors = []
    forbidden = {"$ref", "anyOf", "oneOf", "allOf", "pattern", "minLength", "maxLength"}
    errors += [f"{path}: {key} no permitido" for key in forbidden & schema.keys()]
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            errors.append(f"{path}: falta additionalProperties false")
        if sorted(schema.get("required", [])) != sorted(properties):
            errors.append(f"{path}: required no lista todas las propiedades")
        for name, child in properties.items():
            errors += strict_shape_errors(child, f"{path}.{name}")
    if schema.get("type") == "array":
        errors += strict_shape_errors(schema["items"], f"{path}[]")
    return errors


@pytest.mark.parametrize("name", list(all_schemas()))
def test_every_schema_is_strict_and_in_the_supported_subset(name):
    assert strict_shape_errors(all_schemas()[name]) == []


def test_citations_can_only_point_at_the_allowed_ids():
    schema = citation_schema(IDS)
    assert schema["properties"]["id_evidencia"]["enum"] == IDS


def test_case_file_schema_demands_at_least_one_citation_per_claim():
    claim = case_file_schema(IDS)["properties"]["afirmaciones"]["items"]
    assert claim["properties"]["citas"]["minItems"] == 1
    assert claim["properties"]["tipo"]["enum"] == list(CLAIM_TYPES)
    assert claim["properties"]["atribuida_a"]["type"] == ["string", "null"]


def test_package_schema_has_exactly_three_questions_and_no_legend():
    properties = package_schema(IDS)["properties"]
    assert properties["preguntas"]["minItems"] == properties["preguntas"]["maxItems"] == 3
    assert "leyenda" not in properties


def test_single_shot_schema_nests_the_package_in_the_case_file():
    properties = single_shot_schema(IDS)["properties"]
    assert set(properties) == {"afirmaciones", "vacios", "accion_recomendada", "borrador"}
    assert properties["borrador"]["properties"].keys() == package_schema(IDS)["properties"].keys()


def test_response_format_wraps_a_schema_for_the_openai_compatible_api():
    schema = entailment_schema()
    assert response_format("veredicto", schema) == {
        "type": "json_schema",
        "json_schema": {"name": "veredicto", "strict": True, "schema": schema},
    }


def test_a_schema_with_no_allowed_ids_is_rejected():
    with pytest.raises(ValueError):
        answer_schema([])


CLAIMS_JSON = {
    "afirmaciones": [
        {
            "texto": "El Canal limitará los tránsitos.",
            "tipo": "hecho",
            "atribuida_a": None,
            "citas": [{"id_evidencia": "N-aaa", "campo": "titulo", "pasaje": "limitará"}],
        },
        {
            "texto": "La ministra dice que habrá cambios.",
            "tipo": "declaracion",
            "atribuida_a": "la ministra",
            "citas": [{"id_evidencia": "N-aaa", "campo": "titulo", "pasaje": "cambios"}],
        },
    ]
}


def test_to_claims_numbers_the_claims_in_order():
    claims = to_claims(CLAIMS_JSON)
    assert [c.id_afirmacion for c in claims] == ["A-1", "A-2"]
    assert claims[1].atribuida_a == "la ministra"
    assert claims[0].citas == (Citation(id_evidencia="N-aaa", campo="titulo", pasaje="limitará"),)


def test_to_claims_rejects_a_statement_without_author():
    broken = {"afirmaciones": [{**CLAIMS_JSON["afirmaciones"][1], "atribuida_a": None}]}
    with pytest.raises(ValueError):
        to_claims(broken)


def test_to_claims_turns_a_missing_key_into_a_value_error():
    with pytest.raises(ValueError):
        to_claims({"otra_cosa": []})


PACKAGE_JSON = {
    "titulo": "Titular",
    "brief": "Resumen breve.",
    "enfoque_interes_publico": "Interés público.",
    "preguntas": ["¿Uno?", "¿Dos?", "¿Tres?"],
    "fuentes_y_verificaciones": ["Confirmar con la fuente."],
    "guion": "Guion.",
    "copy_digital": "Copy.",
}


def test_to_package_sets_the_legend_only_for_headline_only_cases():
    assert to_package(PACKAGE_JSON, "titular_metadatos").leyenda == HEADLINE_ONLY_LEGEND
    assert to_package(PACKAGE_JSON, "titular_descripcion").leyenda is None


def test_to_package_does_not_truncate_a_long_brief():
    long_brief = {**PACKAGE_JSON, "brief": " ".join(["palabra"] * 251)}
    with pytest.raises(ValueError, match="brief"):
        to_package(long_brief, "texto_completo")


def test_to_answer_builds_an_answered_answer():
    data = {
        "estado": "respondida",
        "respuesta": "Son 32.",
        "citas": [{"id_evidencia": "N-aaa", "campo": "descripcion", "pasaje": "32"}],
        "motivo_abstencion": None,
        "faltante": None,
        "versiones": [],
    }
    answer = to_answer(data, "Q-1", "¿Cuántos?")
    assert (answer.id_consulta, answer.consulta, answer.estado) == ("Q-1", "¿Cuántos?", "respondida")
    assert answer.citas[0].pasaje == "32"


def test_to_answer_builds_an_abstention_and_ignores_stray_fields():
    data = {
        "estado": "abstencion",
        "respuesta": None,
        "citas": [],
        "motivo_abstencion": "No hay datos.",
        "faltante": "Una cifra oficial.",
        "versiones": [],
    }
    answer = to_answer(data, "Q-4", "¿Cuándo?")
    assert (answer.estado, answer.motivo_abstencion, answer.faltante) == ("abstencion", "No hay datos.", "Una cifra oficial.")


def test_to_answer_builds_a_contradiction_with_both_versions():
    data = {
        "estado": "contradiccion",
        "respuesta": None,
        "citas": [],
        "motivo_abstencion": None,
        "faltante": None,
        "versiones": [
            {"valor": "1,1 %", "alcance": "TVN", "id_evidencia": "N-aaa"},
            {"valor": "2,3 %", "alcance": "Metro Libre", "id_evidencia": "WB-PAN-X-2024"},
        ],
    }
    answer = to_answer(data, "Q-3", "¿Inflación?")
    assert [v.valor for v in answer.versiones] == ["1,1 %", "2,3 %"]


def test_to_answer_turns_an_unknown_state_into_a_value_error():
    with pytest.raises(ValueError):
        to_answer({"estado": "quizas"}, "Q-1", "¿?")
