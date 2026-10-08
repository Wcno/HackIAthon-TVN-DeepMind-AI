"""Compare external news with TVN's loaded coverage before awarding discovery novelty.

Exact replicas are covered. Strong semantic matches with a new reported figure
are potential updates with literal source passages; qualitative differences
remain unverified. An absent semantic match refers only to the loaded snapshot.
"""

from collections.abc import Mapping, Sequence
import hashlib
import json
from difflib import SequenceMatcher
from urllib.parse import urlsplit

import numpy as np

from whoami.generation.verifier import fold, normalize_numbers
from whoami.schemas import Citation, Components, Evidence, Group, Score, TVNCoverage

MATCH_COSINE = .90
COVERAGE_METHOD = "tvn-snapshot-v2"


def is_tvn(row: Mapping[str, str]) -> bool:
    try:
        host = (urlsplit(row.get("url", "")).hostname or "").lower()
    except ValueError:
        host = ""
    return row.get("medio", "").strip().casefold() in {"tvn", "tvn noticias", "tvn media"} or host == "tvn-2.com" or host.endswith(".tvn-2.com")


def tvn_evidence_ids(groups: Sequence[Group], evidence: Mapping[str, Evidence]) -> set[str]:
    """All coverage dependencies, including stories not previously matched to a case."""
    media = {member.id_noticia: member.medio for group in groups for member in group.miembros}
    return {identity for identity, source in evidence.items() if source.tipo == "noticia"
            and is_tvn(source.campos | {"url": source.url, "medio": media.get(identity, source.campos.get("medio", ""))})}


def _text(row: Mapping[str, str]) -> str:
    return " ".join(filter(None, [row.get("titulo", ""), row.get("descripcion", "")]))


def _figures(text: str) -> set:
    return {value for value in normalize_numbers(text) if not 1900 <= value <= 2100}


class CoverageIndex:
    def __init__(self, rows: Sequence[Mapping[str, str]], vectors: np.ndarray | None = None):
        self.rows = rows
        self.vectors = vectors
        self.tvn = [i for i, row in enumerate(rows) if is_tvn(row)]
        self.texts = [fold(_text(row)) for row in rows]
        self.titles = [fold(row.get("titulo", "")) for row in rows]
        self.words = [set(title.split()) for title in self.titles]
        content = [{key: row.get(key, "") for key in ("id_noticia", "titulo", "descripcion", "medio", "url")}
                   for row in rows]
        self.snapshot_sha256 = hashlib.sha256(json.dumps(sorted(content, key=lambda row: row["id_noticia"]),
                                                        sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def assess(self, indices: Sequence[int]) -> TVNCoverage:
        return self._assess(indices).model_copy(update={"snapshot_sha256": self.snapshot_sha256, "metodo": COVERAGE_METHOD})

    def _assess(self, indices: Sequence[int]) -> TVNCoverage:
        external = [i for i in indices if not is_tvn(self.rows[i])]
        own = [self.rows[i]["id_noticia"] for i in indices if is_tvn(self.rows[i])]
        if not external:
            return TVNCoverage(estado="cubierto", razon="Ya publicado por TVN: no es un descubrimiento externo.", ids_tvn=tuple(own))
        if not self.tvn:
            return TVNCoverage(estado="no_comprobada", razon="No hay cobertura de TVN cargada para comparar.")
        matches, new, uncertain, unmatched = set(own), [], False, False
        for index in external:
            row = self.rows[index]
            text = self.texts[index]
            exact = [i for i in self.tvn if text and text in self.texts[i]]
            if exact:
                matches.update(self.rows[i]["id_noticia"] for i in exact)
                continue
            same_title = [i for i in self.tvn if self.titles[index] and self.titles[index] == self.titles[i]]
            if same_title:
                candidates = same_title
            elif self.vectors is not None:
                candidates = [i for i in self.tvn if float(self.vectors[index] @ self.vectors[i]) >= MATCH_COSINE]
            else:
                candidates = [i for i in self.tvn if len(self.words[index] & self.words[i]) / max(len(self.words[index] | self.words[i]), 1) >= .8
                              and SequenceMatcher(None, self.titles[index], self.titles[i]).ratio() >= .9]
            if candidates:
                matches.update(self.rows[i]["id_noticia"] for i in candidates)
                known = set().union(*(_figures(_text(self.rows[i])) for i in candidates))
                fields = [(field, row.get(field, "")) for field in ("titulo", "descripcion")]
                additions = [Citation(id_evidencia=row["id_noticia"], campo=field, pasaje=value)
                             for field, value in fields if _figures(value) - known]
                if additions:
                    new.extend(additions)
                elif same_title:
                    continue  # The core headline is already covered, even when descriptions differ.
                else:
                    uncertain = True
            else:
                unmatched = True
        if new:
            return TVNCoverage(estado="dato_nuevo", razon="Una fuente externa reporta una cifra ausente de la cobertura TVN coincidente; verificar la actualización.",
                               ids_tvn=tuple(sorted(matches)), pasajes_nuevos=tuple(dict.fromkeys(new)))
        if uncertain or (unmatched and self.vectors is None):
            return TVNCoverage(estado="no_comprobada", razon="La comparación no confirma novedad; revisar el alcance y las fuentes.", ids_tvn=tuple(sorted(matches)))
        if unmatched:
            return TVNCoverage(estado="sin_coincidencia", razon="Sin coincidencia en la cobertura TVN disponible; verificar publicaciones fuera de este snapshot.", ids_tvn=tuple(sorted(matches)))
        return TVNCoverage(estado="cubierto", razon="La noticia externa repite contenido presente en el snapshot TVN.", ids_tvn=tuple(sorted(matches)))


def coverage_score(score: Score, assessment: TVNCoverage) -> Score:
    value = score.componentes.N
    if assessment.estado in ("cubierto", "no_comprobada"):
        value = 0.
    elif assessment.estado == "dato_nuevo":
        value = min(value, .75)
    components = Components.model_validate(score.componentes.model_dump() | {"N": value})
    return Score.from_components(components, score.justificaciones | {"N": assessment.razon})


def assess_legacy_groups(groups: Sequence[Group], evidence: Mapping[str, Evidence]) -> list[Group]:
    members = {m.id_noticia: m for group in groups for m in group.miembros}
    rows = []
    for key, item in evidence.items():
        if item.tipo == "noticia":
            member = members.get(key)
            rows.append(item.campos | {"id_noticia": key, "url": item.url,
                        "titulo": item.campos.get("titulo", item.titulo),
                        "medio": member.medio if member else item.campos.get("medio", "")})
    index = CoverageIndex(rows)
    positions = {row["id_noticia"]: i for i, row in enumerate(rows)}
    result = []
    for group in groups:
        cached = group.cobertura_tvn
        assessment = cached if (cached and cached.snapshot_sha256 == index.snapshot_sha256
                                and cached.metodo == COVERAGE_METHOD) else index.assess([positions[m.id_noticia] for m in group.miembros])
        result.append(group.model_copy(update={"cobertura_tvn": assessment, "puntaje": coverage_score(group.puntaje, assessment)}))
    return result
