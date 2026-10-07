"""Screen projections over the persistent repository, independent of HTTP."""

import json
import hashlib
from pathlib import Path

from whoami.backend.gemini import GenerationUnavailable
from whoami.backend.repository import EditorialRepository
from whoami.contracts import TOPIC_LABELS
from whoami.schemas import Group, sort_inbox


class EditorialService:
    def __init__(self, repository: EditorialRepository):
        self.repository = repository

    def inbox(self, *, topic: str | None = None) -> list[dict]:
        groups = [Group.model_validate(group) for group in self.repository.records("group")]
        if topic:
            groups = [group for group in groups if group.tema == topic]
        return [self.group(group.id_grupo) for group in sort_inbox(groups)]

    def group(self, group_id: str) -> dict:
        group = self.repository.record("group", group_id)
        members = group["miembros"]
        group.update(n_noticias=len(members), n_medios=len({member["medio"] for member in members}),
                     n_procedencias=len({member["procedencia"] for member in members}),
                     tema_etiqueta=TOPIC_LABELS.get(group["tema"], group["tema"]))
        group["estado_revision"] = self.repository.case(group["id_caso"])["estado_revision"] if group.get("id_caso") else "nuevo"
        for context in group["contexto"]:
            fields = self.repository.record("evidence", context["id_evidencia"])["campos"]
            context.update(periodo=fields["periodo"], unidad=fields["unidad"], valor=fields["valor"] or None)
        return group

    def case(self, case_id: str) -> dict:
        return self.repository.case(case_id)

    def query(self, query: str) -> dict:
        normalized = " ".join(query.split()).casefold()
        for answer in self.repository.records("answer"):
            if " ".join(answer["consulta"].split()).casefold() == normalized:
                return answer
        raise GenerationUnavailable("sin conexión: solo consultas precalculadas; esta consulta no está disponible")


def quality_report(directory: Path) -> dict:
    reports = {}
    for filename in ("calidad_noticias.json", "calidad_indicadores.json", "calidad_inec.json", "calidad_eventos.json"):
        path = directory / filename
        reports[filename] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"available": False}
    manifest = directory.parent / "manifest.json"
    reports["manifest"] = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"available": False}
    if manifest.exists():
        root = directory.parent.resolve()
        hashes = reports["manifest"].get("sha256", {})
        missing, mismatches, unsafe = [], [], []
        for name, expected in hashes.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root):
                unsafe.append(name)
            elif not path.is_file():
                missing.append(name)
            else:
                with path.open("rb") as source:
                    actual = hashlib.file_digest(source, "sha256").hexdigest()
                if actual != expected:
                    mismatches.append(name)
        status = "verified" if hashes and not (missing or mismatches or unsafe) else "incomplete"
        if mismatches or unsafe:
            status = "invalid"
        reports["manifest"]["integrity"] = {
            "status": status, "expected": len(hashes), "missing": missing,
            "mismatches": mismatches, "unsafe_paths": unsafe,
        }
    return reports
