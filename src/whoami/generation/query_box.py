"""The query box: retrieve, gate, answer, verify. It abstains rather than answer without verified citations."""

from collections.abc import Mapping, Sequence
from typing import Any

from whoami.generation.jsonschemas import answer_schema, response_format, to_answer, to_claims
from whoami.generation.prompting import CosineGate, build_messages, complete_json
from whoami.generation.retrieval import Retriever
from whoami.generation.verifier import check_citations, check_claim, normalize_numbers, unsupported_numbers
from whoami.generation.version_citations import enrich_version_citations, support_version
from whoami.llm.client import LLMError
from whoami.schemas import Answer, Citation, ContradictionVersion, Evidence

TOP_K = 8
#: Gemma can degenerate into endless output inside JSON; a cap turns that into a fast, uncached failure.
ANSWER_MAX_TOKENS = 800
UNVERIFIABLE_REASON = "las citas generadas no se pudieron verificar"
INVALID_ANSWER_REASON = "el modelo no devolvió una respuesta válida"

TASK = (
    "Responde la consulta solo con las fuentes. "
    "estado=respondida: respuesta breve con citas literales. "
    "estado=abstencion: si las fuentes no responden, con motivo_abstencion y faltante. "
    "estado=contradiccion: si dos fuentes dan valores distintos para lo mismo, con una versión por fuente "
    "(valor, alcance, id_evidencia). Deja en null o vacío lo que no corresponda al estado."
)
STRUCTURED_TASK = (
    TASK + " Para estado=respondida, escribe solo afirmaciones atómicas en afirmaciones: "
    "cada una con texto, tipo, atribuida_a y sus propias citas literales. "
    "El código compone la respuesta exclusivamente de estas afirmaciones verificadas. "
    "Deja respuesta=null y citas=[]: no escribas prosa adicional fuera de afirmaciones. "
    "Para abstencion o contradiccion deja afirmaciones=[]. Conserva país, período y unidad en cifras oficiales."
)


def _abstention(id_consulta: str, consulta: str, motivo: str, faltante: str | None = None) -> Answer:
    return Answer(
        id_consulta=id_consulta,
        consulta=consulta,
        estado="abstencion",
        motivo_abstencion=motivo,
        faltante=faltante or f"Fuentes que respondan directamente: {consulta}",
    )


def _distinct_versions(
    raw: Sequence[Mapping[str, Any]], allowed: set[str], evidences: Mapping[str, Evidence]
) -> list[ContradictionVersion]:
    """Versions that cite a retrieved evidence whose record supports their figures, keeping only the first of each
    value and of each evidence."""
    versions: list[ContradictionVersion] = []
    for item in raw:
        version = support_version(ContradictionVersion.model_validate(item), evidences)
        if (
            version is not None and version.id_evidencia in allowed
            and all(version.valor != v.valor and version.id_evidencia != v.id_evidencia for v in versions)
        ):
            versions.append(version)
    return versions


def _verified(data: Mapping[str, Any], consulta: str, evidences: Mapping[str, Evidence], allowed: set[str], *, structured: bool = False) -> dict:
    """The model's answer reduced to what can be verified, in the shape `to_answer` reads."""
    state = data["estado"]
    if state == "abstencion":
        return {
            "estado": "abstencion",
            "motivo_abstencion": data.get("motivo_abstencion") or "las fuentes no responden la consulta",
            "faltante": data.get("faltante") or f"Fuentes que respondan directamente: {consulta}",
        }
    cited = [c for c in map(Citation.model_validate, data["citas"]) if c.id_evidencia in allowed]
    citations = check_citations(cited, evidences).valid
    text = data.get("respuesta")
    versions = _distinct_versions(data["versiones"], allowed, evidences)
    citations_json = [c.model_dump() for c in citations]
    # Two verified versions with distinct values are a contradiction, whatever state the model chose.
    if len(versions) >= 2:
        citations_json = [c.model_dump() for c in dict.fromkeys([*citations, *(c for v in versions for c in v.citas)])]
        return {"estado": "contradiccion", "citas": citations_json, "versiones": [v.model_dump() for v in versions]}
    if structured and state in ("respondida", "contradiccion"):
        claims = []
        for claim in to_claims({"afirmaciones": data.get("afirmaciones", [])}):
            cited = [citation for citation in claim.citas if citation.id_evidencia in allowed]
            checked = check_citations(cited, evidences)
            if not checked.valid:
                continue
            result = check_claim(claim.model_copy(update={"citas": checked.valid}), evidences)
            if not result.issues:
                claims.append(result.claim)
        if claims:
            citations = tuple(dict.fromkeys(citation for claim in claims for citation in claim.citas))
            return {"estado": "respondida", "respuesta": " ".join(claim.texto for claim in claims),
                    "citas": [citation.model_dump() for citation in citations],
                    "afirmaciones": [claim.model_dump(mode="json", exclude={"id_afirmacion"}) for claim in claims]}
        return {"estado": "abstencion", "motivo_abstencion": UNVERIFIABLE_REASON, "faltante": None}
    if state in ("respondida", "contradiccion") and text and citations and not unsupported_numbers(
        text, citations, evidences
    ):
        return {"estado": "respondida", "respuesta": text, "citas": citations_json}
    return {"estado": "abstencion", "motivo_abstencion": UNVERIFIABLE_REASON, "faltante": None}


def answer_query(
    id_consulta: str,
    consulta: str,
    retriever: Retriever,
    gate: CosineGate,
    evidences: Mapping[str, Evidence],
    llm,
    model: str,
    *,
    structured: bool = False,
) -> Answer:
    hits = [(i, score) for i, score in retriever.search(consulta, TOP_K) if i in evidences]
    decision = gate.decide(consulta)
    if not decision.answerable:
        return _abstention(
            id_consulta, consulta, decision.motivo or "las fuentes recuperadas no responden la consulta", decision.faltante
        )
    ids = [i for i, _ in hits]
    try:
        data = complete_json(
            llm,
            model,
            build_messages(STRUCTURED_TASK if structured else TASK, [evidences[i] for i in ids], user_query=consulta),
            purpose="consulta",
            evidence_ids=ids,
            response_format=response_format("respuesta", answer_schema(ids, structured=structured)),
            max_tokens=ANSWER_MAX_TOKENS,
        )
        cleaned = _verified(data, consulta, evidences, set(ids), structured=structured)
        if cleaned["estado"] == "abstencion":
            return _abstention(id_consulta, consulta, cleaned["motivo_abstencion"], cleaned["faltante"])
        answer = to_answer(cleaned, id_consulta, consulta)
        return enrich_version_citations(answer, evidences) if structured else answer
    except (LLMError, ValueError, KeyError, TypeError, AttributeError):
        return _abstention(id_consulta, consulta, INVALID_ANSWER_REASON)
