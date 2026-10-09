"""Reads and writes the pipeline outputs as JSON Lines (one record per line, UTF-8).

`load` and `write` validate the whole output set, so a malformed record or a broken rule between records is
rejected at the boundary and not discovered by the interface.
"""

import json
from pathlib import Path

from whoami.contracts import (
    DEMO,
    EVIDENCE_FILE,
    FICHAS_FILE,
    GROUPS_FILE,
    OUTPUTS,
    PROCESSED,
    QUERIES_FILE,
    REVIEWS_FILE,
)
from whoami.schemas import CaseFile, Group, OutputSet, ReviewState, verify
from whoami.reviews import bind_reviews, reconcile_reviews

REVIEW_ARCHIVE_FILE = "revisiones_historicas.jsonl"
REVIEW_BINDINGS_FILE = "revisiones_vinculadas.jsonl"

#: Fields of a `fichas.jsonl` record that are copies, added when exporting and ignored when loading.
_EXPORT_ONLY = (
    "ids_fuente",
    "citas",
    "puntaje",
    "componentes",
    "puntaje_detalle",
    "estado_evidencia",
    "estado_revision",
    "titulo",
    "tema",
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def case_file_to_record(case_file: CaseFile, group: Group, review_state: ReviewState) -> dict:
    """§7 `fichas.jsonl` record: the minimum fields first, in the order the challenge lists them.

    Score, evidence state and review state are copied here from their single source (the group and the review
    history). `puntaje` is the number and `componentes` the five values; the rest of the score travels in
    `puntaje_detalle`, and the flat `citas` list repeats the citations of the claims without duplicates.
    """
    data = case_file.model_dump(mode="json")
    score = group.puntaje.model_dump(mode="json")
    citations: list[dict] = []
    for claim in data["afirmaciones"]:
        for citation in claim["citas"]:
            if citation not in citations:
                citations.append(citation)
    record = {
        "id_caso": data.pop("id_caso"),
        "modalidad": data.pop("modalidad"),
        "ids_fuente": case_file.cited_ids,
        "afirmaciones": data.pop("afirmaciones"),
        "citas": citations,
        "puntaje": score["valor"],
        "componentes": score["componentes"],
        "estado_evidencia": group.estado_evidencia,
        "borrador": data.pop("borrador"),
        "estado_revision": review_state,
        "puntaje_detalle": {key: score[key] for key in ("rango", "version_reglas", "justificaciones")},
        "titulo": group.titulo,
        "tema": group.tema,
    }
    return record | data


def case_file_from_record(record: dict) -> CaseFile:
    return CaseFile.model_validate({key: value for key, value in record.items() if key not in _EXPORT_ONLY})


def write(output: OutputSet, data: Path = PROCESSED, outputs: Path = OUTPUTS) -> None:
    """Validates the whole set, then writes groups and evidence to `data` and the rest to `outputs`."""
    verify(output)
    output = bind_reviews(output)
    groups = {group.id_grupo: group for group in output.grupos}
    write_jsonl(data / GROUPS_FILE, [group.model_dump(mode="json") for group in output.grupos])
    write_jsonl(data / EVIDENCE_FILE, [evidence.model_dump(mode="json") for evidence in output.evidencias.values()])
    write_jsonl(
        outputs / FICHAS_FILE,
        [
            case_file_to_record(case_file, groups[case_file.id_grupo], output.review_state(case_file.id_caso))
            for case_file in output.fichas
        ],
    )
    write_jsonl(outputs / QUERIES_FILE, [answer.model_dump(mode="json") for answer in output.consultas])
    write_jsonl(outputs / REVIEWS_FILE, [record.model_dump(mode="json") for record in output.revisiones])
    write_jsonl(outputs / REVIEW_BINDINGS_FILE, [record.model_dump(mode="json") for record in output.revisiones_vinculadas])
    if output.historial_revisiones or (outputs / REVIEW_ARCHIVE_FILE).exists():
        write_jsonl(outputs / REVIEW_ARCHIVE_FILE, [record.model_dump(mode="json") for record in output.historial_revisiones])


def link_live_case_files(groups: list[dict], case_files: list[dict]) -> list[dict]:
    """A case file generated live in the app names its group, but the frozen group file predates it.

    Only a group without a case file is linked; a group naming a different case file stays incoherent."""
    owner = {case["id_grupo"]: case["id_caso"] for case in case_files}
    return [group | {"id_caso": owner[group["id_grupo"]]} if group["id_caso"] is None and group["id_grupo"] in owner else group
            for group in groups]


def load(data: Path = PROCESSED, outputs: Path = OUTPUTS) -> OutputSet:
    """Loads the real pipeline output, rejecting anything that breaks a schema or a rule between records."""
    case_files = [case_file_from_record(record).model_dump() for record in read_jsonl(outputs / FICHAS_FILE)]
    output = OutputSet.model_validate(
        {
            "grupos": link_live_case_files(read_jsonl(data / GROUPS_FILE), case_files),
            "evidencias": {record["id_evidencia"]: record for record in read_jsonl(data / EVIDENCE_FILE)},
            "fichas": case_files,
            "consultas": read_jsonl(outputs / QUERIES_FILE),
            "revisiones": read_jsonl(outputs / REVIEWS_FILE),
            "historial_revisiones": read_jsonl(outputs / REVIEW_ARCHIVE_FILE) if (outputs / REVIEW_ARCHIVE_FILE).exists() else [],
            "revisiones_vinculadas": read_jsonl(outputs / REVIEW_BINDINGS_FILE) if (outputs / REVIEW_BINDINGS_FILE).exists() else [],
        }
    )
    output = reconcile_reviews(output)
    verify(output)
    return output


def load_demo() -> OutputSet:
    """The synthetic set in `data/demo/`: same files and schemas, all in one directory."""
    return load(DEMO, DEMO)
