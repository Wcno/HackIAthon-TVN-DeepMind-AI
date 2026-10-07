"""Screen projections over the persistent repository, independent of HTTP."""

import json
from pathlib import Path

from whoami.backend.gemini import GenerationUnavailable
from whoami.backend.repository import EditorialRepository
from whoami.contracts import DATA, TOPIC_LABELS


class EditorialService:
    def __init__(self, repository: EditorialRepository):
        self.repository = repository

    def inbox(self, *, topic: str | None = None) -> list[dict]:
        groups = [self.group(group["id_grupo"]) for group in self.repository.records("group")]
        if topic:
            groups = [group for group in groups if group["tema"] == topic]
        return sorted(groups, key=lambda group: (-group["puntaje"]["valor"], -group["puntaje"]["componentes"]["U"], group["id_grupo"]))

    def group(self, group_id: str) -> dict:
        group = self.repository.record("group", group_id)
        members = group["miembros"]
        group.update(n_noticias=len(members), n_medios=len({member["medio"] for member in members}),
                     n_procedencias=len({member["procedencia"] for member in members}),
                     tema_etiqueta=TOPIC_LABELS.get(group["tema"], group["tema"]))
        group["estado_revision"] = self.repository.case(group["id_caso"])["estado_revision"] if group.get("id_caso") else "nuevo"
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
    manifest = DATA / "manifest.json"
    reports["manifest"] = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"available": False}
    return reports
