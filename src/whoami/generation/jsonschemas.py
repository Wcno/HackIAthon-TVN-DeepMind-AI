"""Strict output schemas for the model and converters from its JSON to the contract objects.

Schemas use the subset every OpenAI-compatible provider (Gemini included) accepts in strict mode: `type`,
`properties`, `required` (all of them), `additionalProperties: false`, `enum`, `items`, `minItems`/`maxItems`,
and nullability as `"type": ["string", "null"]`.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from whoami.contracts import ANSWER_STATES, CLAIM_TYPES, HEADLINE_ONLY_LEGEND, RESEARCH_QUESTIONS, TEXT_SCOPE_HEADLINE
from whoami.schemas import Answer, Citation, Claim, ContradictionVersion, EditorialPackage

Schema = dict[str, Any]

_STRING: Schema = {"type": "string"}
_NULLABLE_STRING: Schema = {"type": ["string", "null"]}
_BOOLEAN: Schema = {"type": "boolean"}


def _object(properties: Mapping[str, Schema]) -> Schema:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(properties),
        "additionalProperties": False,
    }


def _array(items: Schema, *, min_items: int | None = None, max_items: int | None = None) -> Schema:
    schema: Schema = {"type": "array", "items": items}
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def _id_enum(allowed_ids: Iterable[str]) -> Schema:
    ids = list(dict.fromkeys(allowed_ids))
    if not ids:
        raise ValueError("se necesita al menos un id de evidencia permitido")
    return {"type": "string", "enum": ids}


def response_format(name: str, schema: Schema) -> dict:
    """The `response_format` argument of an OpenAI-compatible chat call."""
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


def citation_schema(allowed_ids: Iterable[str]) -> Schema:
    return _object({"id_evidencia": _id_enum(allowed_ids), "campo": _STRING, "pasaje": _STRING})


def _claim_schema(allowed_ids: Sequence[str]) -> Schema:
    return _object(
        {
            "texto": _STRING,
            "tipo": {"type": "string", "enum": list(CLAIM_TYPES)},
            "atribuida_a": _NULLABLE_STRING,
            "citas": _array(citation_schema(allowed_ids), min_items=1),
        }
    )


def claims_schema(allowed_ids: Sequence[str]) -> Schema:
    return _object({"afirmaciones": _array(_claim_schema(allowed_ids))})


def package_schema() -> Schema:
    """The editorial package; `leyenda` is not asked of the model, code sets it from the text scope."""
    return _object(
        {
            "titulo": _STRING,
            "brief": _STRING,
            "enfoque_interes_publico": _STRING,
            "preguntas": _array(_STRING, min_items=RESEARCH_QUESTIONS, max_items=RESEARCH_QUESTIONS),
            "fuentes_y_verificaciones": _array(_STRING),
            "guion": _STRING,
            "copy_digital": _STRING,
        }
    )


def answer_schema(allowed_ids: Sequence[str]) -> Schema:
    version = _object({"valor": _STRING, "alcance": _STRING, "id_evidencia": _id_enum(allowed_ids)})
    return _object(
        {
            "estado": {"type": "string", "enum": list(ANSWER_STATES)},
            "respuesta": _NULLABLE_STRING,
            "citas": _array(citation_schema(allowed_ids)),
            "motivo_abstencion": _NULLABLE_STRING,
            "faltante": _NULLABLE_STRING,
            "versiones": _array(version),
        }
    )


def entailment_schema() -> Schema:
    return _object(
        {"veredicto": {"type": "string", "enum": ["respaldada", "no_respaldada", "parcial"]}, "motivo": _STRING}
    )


def contradiction_pair_schema() -> Schema:
    """Do two news items of the same group state incompatible things?"""
    return _object(
        {"contradiccion": _BOOLEAN, "descripcion": _STRING, "valor_a": _STRING, "valor_b": _STRING}
    )


# ---------------------------------------------------------------------------------------------------------
# Converters: parsed model JSON to contract objects. Any malformed shape becomes a `ValueError` (Pydantic's `ValidationError` is one).
# ---------------------------------------------------------------------------------------------------------


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _citation(data: Mapping[str, Any]) -> Citation:
    return Citation(id_evidencia=data["id_evidencia"], campo=data["campo"], pasaje=data["pasaje"])


def _converting(function):
    """Makes missing keys and wrong types in model output a `ValueError`, which callers already handle."""

    def convert(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"la respuesta del modelo no tiene la forma esperada: {error!r}") from error

    convert.__name__ = function.__name__
    convert.__doc__ = function.__doc__
    return convert


@_converting
def to_claims(data: Mapping[str, Any]) -> tuple[Claim, ...]:
    """Claims numbered `A-1`, `A-2`... in the order the model wrote them."""
    return tuple(
        Claim(
            id_afirmacion=f"A-{number}",
            texto=item["texto"],
            tipo=item["tipo"],
            atribuida_a=_text_or_none(item.get("atribuida_a")),
            citas=tuple(_citation(c) for c in item["citas"]),
        )
        for number, item in enumerate(data["afirmaciones"], start=1)
    )


@_converting
def to_package(data: Mapping[str, Any], alcance_texto: str) -> EditorialPackage:
    """Nothing is truncated: a brief or copy over the limit raises and the caller decides."""
    return EditorialPackage(
        titulo=data["titulo"],
        brief=data["brief"],
        enfoque_interes_publico=data["enfoque_interes_publico"],
        preguntas=tuple(data["preguntas"]),
        fuentes_y_verificaciones=tuple(data["fuentes_y_verificaciones"]),
        guion=data["guion"],
        copy_digital=data["copy_digital"],
        leyenda=HEADLINE_ONLY_LEGEND if alcance_texto == TEXT_SCOPE_HEADLINE else None,
    )


@_converting
def to_answer(data: Mapping[str, Any], id_consulta: str, consulta: str) -> Answer:
    """Keeps only the fields that belong to the state the model chose."""
    state = data["estado"]
    fields: dict[str, Any] = {}
    if state == "respondida":
        fields = {"respuesta": _text_or_none(data.get("respuesta")), "citas": tuple(_citation(c) for c in data["citas"])}
    elif state == "abstencion":
        fields = {
            "motivo_abstencion": _text_or_none(data.get("motivo_abstencion")),
            "faltante": _text_or_none(data.get("faltante")),
        }
    elif state == "contradiccion":
        fields = {
            "citas": tuple(_citation(c) for c in data.get("citas", ())),
            "versiones": tuple(
                ContradictionVersion(valor=v["valor"], alcance=v["alcance"], id_evidencia=v["id_evidencia"])
                for v in data["versiones"]
            ),
        }
    return Answer(id_consulta=id_consulta, consulta=consulta, estado=state, **fields)
