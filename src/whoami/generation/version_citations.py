"""Attach explicit source fields/passages to contradictory values without a model call."""

import re
from collections.abc import Mapping

from whoami.generation.verifier import fold, normalize_numbers
from whoami.schemas import Answer, Citation, ContradictionVersion, Evidence, citation_errors


def _contains_value(value: str, passage: str) -> bool:
    return bool(re.search(r"\b" + re.escape(fold(value)) + r"\b", fold(passage)))


def version_citations_valid(version: ContradictionVersion, evidence: Mapping[str, Evidence]) -> bool:
    if not version.citas or citation_errors(version.citas, evidence):
        return False
    if any(citation.id_evidencia != version.id_evidencia for citation in version.citas):
        return False
    value_numbers = set(normalize_numbers(version.valor))
    if not value_numbers and not any(_contains_value(version.valor, citation.pasaje) for citation in version.citas):
        return False
    cited_numbers = {number for citation in version.citas for number in normalize_numbers(citation.pasaje)}
    return value_numbers | set(normalize_numbers(version.alcance)) <= cited_numbers


def support_version(version: ContradictionVersion, evidence: Mapping[str, Evidence]) -> ContradictionVersion | None:
    source = evidence.get(version.id_evidencia)
    if source is None:
        return None
    value_numbers = set(normalize_numbers(version.valor))
    required = value_numbers | set(normalize_numbers(version.alcance))
    selected = []
    if not value_numbers:
        literal_fields = [(field, text) for field, text in source.campos.items() if _contains_value(version.valor, text)]
        if not literal_fields:
            return None
        field, text = min(literal_fields, key=lambda item: (len(item[1]), item[0]))
        selected.append(Citation(id_evidencia=source.id_evidencia, campo=field, pasaje=text))
        required -= set(normalize_numbers(text))
    if required:
        remaining = set(required)
        fields = sorted(source.campos.items(), key=lambda item: (-len(set(normalize_numbers(item[1])) & required), len(item[1]), item[0]))
        for field, text in fields:
            contribution = set(normalize_numbers(text)) & remaining
            if contribution:
                selected.append(Citation(id_evidencia=source.id_evidencia, campo=field, pasaje=text))
                remaining -= contribution
            if not remaining:
                break
        if remaining:
            return None
    return version.model_copy(update={"citas": tuple(selected)})


def enrich_version_citations(answer: Answer, evidence: Mapping[str, Evidence]) -> Answer:
    if answer.estado != "contradiccion":
        return answer
    versions = tuple(support_version(version, evidence) or version.model_copy(update={"citas": ()})
                     for version in answer.versiones)
    citations = tuple(dict.fromkeys([*answer.citas, *(citation for version in versions for citation in version.citas)]))
    return Answer.model_validate(answer.model_dump() | {"versiones": versions, "citas": citations})
