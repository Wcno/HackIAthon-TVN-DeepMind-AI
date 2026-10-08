"""Refreshes the official evidence and each group's context label in `processed/`, without grouping again.

Grouping and topics may come from a model, so they are kept as written; only what the official files determine changes.
"""

from collections.abc import Mapping
from pathlib import Path

from whoami.contracts import EVIDENCE_FILE, GROUPS_FILE, PROCESSED
from whoami.pipeline.context import context_label
from whoami.schemas import Evidence, Group
from whoami.store import read_jsonl, write_jsonl


def refresh_official(official: Mapping[str, Evidence], data: Path = PROCESSED) -> None:
    """Replaces the evidence records whose id is official and relabels every context link from the new record."""
    evidences = {
        record["id_evidencia"]: official.get(record["id_evidencia"]) or Evidence.model_validate(record)
        for record in read_jsonl(data / EVIDENCE_FILE)
    }
    groups = [Group.model_validate(record) for record in read_jsonl(data / GROUPS_FILE)]
    relabeled = [
        group.model_copy(
            update={
                "contexto": tuple(
                    link.model_copy(update={"etiqueta": context_label(evidences[link.id_evidencia])}) for link in group.contexto
                )
            }
        )
        for group in groups
    ]
    write_jsonl(data / GROUPS_FILE, [group.model_dump(mode="json") for group in relabeled])
    write_jsonl(data / EVIDENCE_FILE, [evidence.model_dump(mode="json") for evidence in evidences.values()])
