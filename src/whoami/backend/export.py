"""Export the live SQLite review cycle into G2's delivery files."""

import os
import tempfile
from pathlib import Path

from whoami.backend.repository import EditorialRepository
from whoami.contracts import FICHAS_FILE, QUERIES_FILE, REVIEWS_FILE
from whoami.schemas import OutputSet, verify
from whoami.store import case_file_to_record, write_jsonl


def export_backend(repository: EditorialRepository, directory: Path) -> dict[str, int]:
    bundle = repository.snapshot_bundle()
    output = OutputSet.model_validate({
        "grupos": bundle.groups,
        "evidencias": {item["id_evidencia"]: item for item in bundle.evidence},
        "fichas": bundle.cases,
        "consultas": bundle.answers,
        "revisiones": bundle.reviews,
    })
    verify(output)
    groups = {group.id_grupo: group for group in output.grupos}
    directory.mkdir(parents=True, exist_ok=True)
    records = {
        FICHAS_FILE: [case_file_to_record(case, groups[case.id_grupo], output.review_state(case.id_caso))
                      for case in output.fichas],
        REVIEWS_FILE: [review.model_dump(mode="json") for review in output.revisiones],
        QUERIES_FILE: [answer.model_dump(mode="json") for answer in output.consultas],
    }
    # Stop the server before exporting into a shared delivery directory. Each
    # individual file is replaced atomically; this is not a multi-file transaction.
    with tempfile.TemporaryDirectory(prefix=".backend-export-", dir=directory) as temporary:
        staging = Path(temporary)
        for name, rows in records.items():
            write_jsonl(staging / name, rows)
        for name in records:
            os.replace(staging / name, directory / name)
    return {name: len(rows) for name, rows in records.items()}
