import json
import shutil

from whoami.contracts import DEMO, EVIDENCE_FILE, GROUPS_FILE
from whoami.pipeline.official import refresh_official
from whoami.schemas import Evidence, Group
from whoami.store import read_jsonl

INEC_ID = "INEC-ipc_var_interanual-2026-08"


def demo_copy(tmp_path):
    for name in (GROUPS_FILE, EVIDENCE_FILE):
        shutil.copy(DEMO / name, tmp_path / name)
    return tmp_path


def renamed_inec(tmp_path) -> Evidence:
    record = next(r for r in read_jsonl(tmp_path / EVIDENCE_FILE) if r["id_evidencia"] == INEC_ID)
    return Evidence.model_validate(record | {"campos": record["campos"] | {"serie": "IPC, variación interanual (revisada)"}})


def test_refresh_relabels_context_and_replaces_only_the_official_evidence(tmp_path):
    data = demo_copy(tmp_path)
    groups_before, evidences_before = read_jsonl(data / GROUPS_FILE), read_jsonl(data / EVIDENCE_FILE)

    refresh_official({INEC_ID: renamed_inec(data)}, data)

    groups, evidences = read_jsonl(data / GROUPS_FILE), read_jsonl(data / EVIDENCE_FILE)
    labels = {c["id_evidencia"]: c["etiqueta"] for g in groups for c in g["contexto"]}
    assert labels[INEC_ID] == "IPC, variación interanual (revisada)"
    # Groups written back always carry the optional fields of the current schema (e.g. `cobertura_tvn`), old files may not.
    normalized = lambda gs: [Group.model_validate(g).model_dump(mode="json") | {"contexto": None} for g in gs]  # noqa: E731
    assert normalized(groups) == normalized(groups_before)
    unlabeled = lambda gs: json.dumps([[{**c, "etiqueta": ""} for c in g["contexto"]] for g in gs])  # noqa: E731
    assert unlabeled(groups) == unlabeled(groups_before)
    assert [e["id_evidencia"] for e in evidences] == [e["id_evidencia"] for e in evidences_before]
    assert [e for e in evidences if e["id_evidencia"] != INEC_ID] == [e for e in evidences_before if e["id_evidencia"] != INEC_ID]


def test_refresh_is_idempotent(tmp_path):
    data = demo_copy(tmp_path)
    refresh_official({}, data)
    once = {name: (data / name).read_bytes() for name in (GROUPS_FILE, EVIDENCE_FILE)}

    refresh_official({}, data)

    assert {name: (data / name).read_bytes() for name in once} == once
