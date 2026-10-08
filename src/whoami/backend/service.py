"""Screen projections over the persistent repository, independent of HTTP."""

import hashlib
import json
import unicodedata
from pathlib import Path

from whoami.backend.gemini import GenerationUnavailable
from whoami.backend.repository import EditorialRepository
from whoami.contracts import TOPIC_LABELS
from whoami.schemas import Group, sort_inbox
from whoami.schemas import Evidence
from whoami.pipeline.tvn_coverage import assess_legacy_groups


def comparable(question: str) -> str:
    """A question without case, accents, inverted marks or spacing differences, to match it with a precalculated one."""
    plain = "".join(c for c in unicodedata.normalize("NFD", question) if not unicodedata.combining(c))
    return " ".join(plain.replace("¿", " ").replace("?", " ").split()).casefold()


class EditorialService:
    def __init__(self, repository: EditorialRepository, images: dict[str, dict] | None = None):
        self.repository = repository
        self.images = images or {}
        self._coverage_key = None
        self._coverage_groups = {}

    def _assessed_groups(self) -> dict[str, Group]:
        raw = self.repository.records("group")
        evidence = self.repository.records("evidence")
        key = hashlib.sha256(json.dumps([raw, evidence], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if key != self._coverage_key:
            groups = [Group.model_validate(row) for row in raw]
            sources = {row["id_evidencia"]: Evidence.model_validate(row) for row in evidence}
            self._coverage_groups = {g.id_grupo: g for g in assess_legacy_groups(groups, sources)}
            self._coverage_key = key
        return self._coverage_groups

    def inbox(self, *, topic: str | None = None, include_covered: bool = False, covered_only: bool = False) -> list[dict]:
        """Ranked topics. By default those TVN already covered stay out; `include_covered` adds them, `covered_only` lists just them."""
        groups = [g for g in self._assessed_groups().values()
                  if include_covered or (g.cobertura_tvn.estado == "cubierto") == covered_only]
        if topic:
            groups = [group for group in groups if group.tema == topic]
        return [self._project_group(group) for group in sort_inbox(groups)]

    def group(self, group_id: str) -> dict:
        assessed = self._assessed_groups()
        if group_id not in assessed:
            return self.repository.record("group", group_id)
        return self._project_group(assessed[group_id])

    def _project_group(self, assessed: Group) -> dict:
        group = assessed.model_dump(mode="json")
        members = group["miembros"]
        group.update(n_noticias=len(members), n_medios=len({member["medio"] for member in members}),
                     n_procedencias=len({member["procedencia"] for member in members}),
                     tema_etiqueta=TOPIC_LABELS.get(group["tema"], group["tema"]),
                     imagen=next((self.images[member["id_noticia"]] for member in members
                                  if member["id_noticia"] in self.images), None))
        group["estado_revision"] = self.repository.case(group["id_caso"])["estado_revision"] if group.get("id_caso") else "nuevo"
        for context in group["contexto"]:
            fields = self.repository.record("evidence", context["id_evidencia"])["campos"]
            context.update(periodo=fields["periodo"], unidad=fields["unidad"], valor=fields["valor"] or None,
                           base=fields.get("base"), frecuencia=fields.get("frecuencia"))
        return group

    def case(self, case_id: str) -> dict:
        case = self.repository.case(case_id)
        group = self.group(case["id_grupo"])
        return case | {"puntaje": group["puntaje"]["valor"], "componentes": group["puntaje"]["componentes"],
                       "cobertura_tvn": group["cobertura_tvn"]}

    def query(self, query: str) -> dict:
        normalized = comparable(query)
        for answer in self.repository.records("answer"):
            if comparable(answer["consulta"]) == normalized:
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
