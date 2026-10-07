"""The only boundary that imports G2's file contract."""

from dataclasses import dataclass
from pathlib import Path

from whoami import store
from whoami.schemas import Evidencia, Respuesta, errores_de_citas


@dataclass(frozen=True)
class PipelineBundle:
    groups: tuple[dict, ...]
    evidence: tuple[dict, ...]
    cases: tuple[dict, ...]
    answers: tuple[dict, ...]
    reviews: tuple[dict, ...]


def load_pipeline(data_directory: Path, output_directory: Path) -> PipelineBundle:
    package = store.cargar(data_directory, output_directory)
    return PipelineBundle(
        groups=tuple(store.a_dict(group) for group in package.grupos),
        evidence=tuple(store.a_dict(item) for item in package.evidencias.values()),
        cases=tuple(store.a_registro_ficha(case) for case in package.fichas),
        answers=tuple(store.a_dict(answer) for answer in package.consultas),
        reviews=tuple(store.a_dict(review) for review in package.revisiones),
    )


def validate_answer(answer: dict, evidence: dict[str, dict]) -> None:
    response = store.de_dict(Respuesta, answer)
    records = {key: store.de_dict(Evidencia, value) for key, value in evidence.items()}
    errors = errores_de_citas(response.citas, records)
    errors.extend(f"Unknown evidence: {version.id_evidencia}" for version in response.versiones
                  if version.id_evidencia not in records)
    if errors:
        raise ValueError("Invalid answer citations: " + "; ".join(errors))
