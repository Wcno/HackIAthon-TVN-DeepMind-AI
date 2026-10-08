"""Load and validate the G2 contract at the backend input boundary."""

from dataclasses import dataclass
from pathlib import Path

from whoami import store
from whoami.schemas import Answer, Evidence, citation_errors


@dataclass(frozen=True)
class PipelineBundle:
    groups: tuple[dict, ...]
    evidence: tuple[dict, ...]
    cases: tuple[dict, ...]
    answers: tuple[dict, ...]
    reviews: tuple[dict, ...]


def load_pipeline(data_directory: Path, output_directory: Path) -> PipelineBundle:
    package = store.load(data_directory, output_directory)
    return PipelineBundle(
        groups=tuple(group.model_dump(mode="json") for group in package.grupos),
        evidence=tuple(item.model_dump(mode="json") for item in package.evidencias.values()),
        cases=tuple(case.model_dump(mode="json") for case in package.fichas),
        answers=tuple(answer.model_dump(mode="json") for answer in package.consultas),
        reviews=tuple(review.model_dump(mode="json") for review in package.revisiones),
    )


def validate_answer(answer: dict, evidence: dict[str, dict]) -> None:
    response = Answer.model_validate(answer)
    records = {key: Evidence.model_validate(value) for key, value in evidence.items()}
    errors = citation_errors(response.citas, records)
    errors.extend(f"Unknown evidence: {version.id_evidencia}" for version in response.versiones
                  if version.id_evidencia not in records)
    if errors:
        raise ValueError("Invalid answer citations: " + "; ".join(errors))
