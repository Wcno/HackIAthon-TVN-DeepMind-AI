"""Pipeline output schemas shared by the `ai`, `api` and frontend lanes (issue G2).

Python names are English; field names and values follow §7 and the challenge vocabulary, in Spanish.
Every model is frozen and rejects unknown fields, and each rule of the challenge that can be checked from the
data alone is enforced when a record is built, so a lane cannot hand over something another lane must distrust.
Rules that span several records live in `verify`.

Each fact is stored once. The review state lives only in the review history; a case file takes its score and
evidence state from its group; official figures are read from their `Evidence`.
"""

import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from whoami.contracts import (
    BRIEF_MAX_WORDS,
    COPY_MAX_WORDS,
    EVIDENCE_PREFIXES,
    HEADLINE_ONLY_LEGEND,
    MODALITY,
    RESEARCH_QUESTIONS,
    REVIEW_TRANSITIONS,
    RULES_VERSION,
    SCORE_RANGES,
    SCORE_WEIGHTS,
    TEXT_SCOPE_HEADLINE,
    AnswerState,
    ClaimType,
    EvidenceKind,
    EvidenceState,
    Modality,
    ReviewState,
    ScoreRange,
    TextScope,
    TopicOrNone,
)

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("debe estar en UTC (sufijo Z)")
    return value


#: §7: ISO 8601 in UTC. The interface converts to Panama time for display.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_require_utc)]


def parse_utc(text: str) -> datetime:
    """`2026-10-05T14:00:00Z` to an aware UTC datetime; anything else is an error."""
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError(f"se esperaba una fecha UTC con sufijo Z: {text!r}")
    return _require_utc(value)


class Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------------------------------------


class Components(Schema):
    """R, I, U, N, E of the attention score, each in 0-1."""

    R: UnitFloat
    I: UnitFloat  # noqa: E741
    U: UnitFloat
    N: UnitFloat
    E: UnitFloat


def compute_score(components: Components) -> float:
    return round(sum(weight * getattr(components, name) for name, weight in SCORE_WEIGHTS.items()), 2)


def range_of(score: float) -> ScoreRange:
    if not (isinstance(score, int | float) and math.isfinite(score) and 0 <= score <= 100):
        raise ValueError(f"puntaje fuera de 0-100: {score!r}")
    for name, low, high in SCORE_RANGES:
        if low <= score < high or (name == "alto" and score == 100):
            return name  # type: ignore[return-value]
    raise AssertionError("unreachable: ranges cover 0-100")


class Score(Schema):
    """Attention score with its components. Value and range are derived, never trusted from a lane."""

    componentes: Components
    valor: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    rango: ScoreRange
    version_reglas: NonEmpty
    justificaciones: dict[str, NonEmpty]

    @model_validator(mode="after")
    def _derived_fields_match(self) -> Self:
        missing = [name for name in SCORE_WEIGHTS if name not in self.justificaciones]
        if missing:
            raise ValueError(f"falta justificación para los componentes: {', '.join(missing)}")
        expected = compute_score(self.componentes)
        if self.valor != expected:
            raise ValueError(f"valor {self.valor} no coincide con los componentes ({expected})")
        if self.rango != range_of(self.valor):
            raise ValueError(f"rango {self.rango!r} no corresponde al valor {self.valor}")
        return self

    @classmethod
    def from_components(cls, components: Components, justifications: Mapping[str, str]) -> Self:
        value = compute_score(components)
        return cls(
            componentes=components,
            valor=value,
            rango=range_of(value),
            version_reglas=RULES_VERSION,
            justificaciones=dict(justifications),
        )


# ---------------------------------------------------------------------------------------------------------
# Evidence and claims
# ---------------------------------------------------------------------------------------------------------


class Evidence(Schema):
    """One citable record: a news item, an official indicator, an INEC series point or an earthquake."""

    id_evidencia: NonEmpty
    tipo: EvidenceKind
    titulo: NonEmpty
    url: NonEmpty
    fecha: UtcDatetime | None
    campos: dict[str, str]

    @field_validator("campos")
    @classmethod
    def _has_something_to_cite(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("campos no puede estar vacío: no habría qué citar")
        return value

    @model_validator(mode="after")
    def _id_prefix_matches_type(self) -> Self:
        prefix = EVIDENCE_PREFIXES[self.tipo]
        if not self.id_evidencia.startswith(prefix):
            raise ValueError(f"id_evidencia {self.id_evidencia!r} debe empezar por {prefix!r} para tipo {self.tipo!r}")
        return self


class Citation(Schema):
    """Points at a passage of one field of one evidence record; a bare URL is not a citation (§7)."""

    id_evidencia: NonEmpty
    campo: NonEmpty
    pasaje: NonEmpty


def citation_errors(citations: Iterable[Citation], evidences: Mapping[str, Evidence]) -> list[str]:
    """Deterministic check of §7: the id exists, the field exists and the passage is literal."""
    errors = []
    for citation in citations:
        evidence = evidences.get(citation.id_evidencia)
        if evidence is None:
            errors.append(f"{citation.id_evidencia}: la evidencia no existe")
        elif citation.campo not in evidence.campos:
            errors.append(f"{citation.id_evidencia}: el campo {citation.campo!r} no existe")
        elif citation.pasaje not in evidence.campos[citation.campo]:
            errors.append(f"{citation.id_evidencia}: el pasaje no es literal en {citation.campo!r}: {citation.pasaje!r}")
    return errors


class Claim(Schema):
    """A cited claim of a case file or structured answer. Accusations are attributed statements (§8)."""

    id_afirmacion: NonEmpty
    texto: NonEmpty
    tipo: ClaimType
    citas: Annotated[tuple[Citation, ...], Field(min_length=1)]
    atribuida_a: NonEmpty | None = None

    @model_validator(mode="after")
    def _statements_name_their_author(self) -> Self:
        if self.tipo == "declaracion" and self.atribuida_a is None:
            raise ValueError(f"la declaración {self.id_afirmacion} necesita atribuida_a")
        return self


class EditorialPackage(Schema):
    """§3 editorial package. Never invents interviews, quotes or available images."""

    titulo: NonEmpty
    brief: NonEmpty
    enfoque_interes_publico: NonEmpty
    preguntas: Annotated[tuple[NonEmpty, ...], Field(min_length=RESEARCH_QUESTIONS, max_length=RESEARCH_QUESTIONS)]
    fuentes_y_verificaciones: tuple[NonEmpty, ...]
    guion: NonEmpty
    copy_digital: NonEmpty
    leyenda: NonEmpty | None
    respaldo: dict[str, tuple[str, ...]] | None = None

    @field_validator("brief")
    @classmethod
    def _brief_length(cls, value: str) -> str:
        if len(value.split()) > BRIEF_MAX_WORDS:
            raise ValueError(f"brief excede {BRIEF_MAX_WORDS} palabras")
        return value

    @field_validator("copy_digital")
    @classmethod
    def _copy_length(cls, value: str) -> str:
        if len(value.split()) > COPY_MAX_WORDS:
            raise ValueError(f"copy_digital excede {COPY_MAX_WORDS} palabras")
        return value


class ContradictionVersion(Schema):
    valor: NonEmpty
    alcance: NonEmpty
    id_evidencia: NonEmpty
    citas: tuple[Citation, ...] = ()

    @model_validator(mode="after")
    def _citations_belong_to_the_version(self) -> Self:
        if any(citation.id_evidencia != self.id_evidencia for citation in self.citas):
            raise ValueError("las citas de una versión deben pertenecer a su evidencia")
        return self


class Contradiction(Schema):
    """Incompatible claims inside one group: both versions are shown and verification stays pending (T05)."""

    descripcion: NonEmpty
    versiones: Annotated[tuple[ContradictionVersion, ...], Field(min_length=2)]


class CaseFile(Schema):
    """One case of `fichas.jsonl` (§7).

    Score, evidence state, title and topic come from the group (`id_grupo`), and the review state from the
    review history; `store.case_file_to_record` adds them when it exports the §7 record.
    """

    id_caso: NonEmpty
    modalidad: Modality = MODALITY
    id_grupo: NonEmpty
    alcance_texto: TextScope
    afirmaciones: Annotated[tuple[Claim, ...], Field(min_length=1)]
    borrador: EditorialPackage | None
    vacios: tuple[NonEmpty, ...]
    contradicciones: tuple[Contradiction, ...]
    accion_recomendada: NonEmpty
    sintetico: bool = False
    metodo_generacion: str | None = Field(default=None, pattern="^seleccion-afirmaciones-v1$")

    @model_validator(mode="after")
    def _headline_only_drafts_say_so(self) -> Self:
        if (
            self.borrador is not None
            and self.alcance_texto == TEXT_SCOPE_HEADLINE
            and self.borrador.leyenda != HEADLINE_ONLY_LEGEND
        ):
            raise ValueError(f"leyenda del borrador debe ser {HEADLINE_ONLY_LEGEND!r} cuando solo hay titular/metadatos")
        return self

    @property
    def cited_ids(self) -> list[str]:
        """Evidence ids this case file cites, in order of first appearance."""
        return list(dict.fromkeys(c.id_evidencia for claim in self.afirmaciones for c in claim.citas))


# ---------------------------------------------------------------------------------------------------------
# Groups, inbox, answers, reviews
# ---------------------------------------------------------------------------------------------------------


class Member(Schema):
    """A news item inside a group. `procedencia` is who produced the content: an agency republished by
    three outlets is one provenance, so repetition is not read as corroboration (CU-03)."""

    id_noticia: NonEmpty
    titulo: NonEmpty
    url: NonEmpty
    medio: NonEmpty
    procedencia: NonEmpty
    fecha_publicacion: UtcDatetime
    alcance_texto: TextScope
    recirculada_en: UtcDatetime | None

    @model_validator(mode="after")
    def _valid_news_item(self) -> Self:
        prefix = EVIDENCE_PREFIXES["noticia"]
        if not self.id_noticia.startswith(prefix):
            raise ValueError(f"id_noticia debe empezar por {prefix!r}: {self.id_noticia!r}")
        if self.recirculada_en is not None and self.recirculada_en <= self.fecha_publicacion:
            raise ValueError("recirculada_en debe ser posterior a la fecha de publicación original (T03)")
        return self


class ContextLink(Schema):
    """An official indicator or event linked to a group. Period, unit and value are read from its `Evidence`."""

    id_evidencia: NonEmpty
    etiqueta: NonEmpty
    pais: NonEmpty
    limitaciones: NonEmpty
    razon: NonEmpty

    @model_validator(mode="after")
    def _is_official_evidence(self) -> Self:
        news_prefix = EVIDENCE_PREFIXES["noticia"]
        if self.id_evidencia.startswith(news_prefix) or not any(
            self.id_evidencia.startswith(prefix) for prefix in EVIDENCE_PREFIXES.values()
        ):
            raise ValueError(f"id_evidencia debe ser de un indicador, serie INEC o sismo: {self.id_evidencia!r}")
        return self


class TVNCoverage(Schema):
    """Discovery assessment against the loaded TVN snapshot, never the entire web."""

    estado: str = Field(pattern="^(cubierto|dato_nuevo|sin_coincidencia|no_comprobada)$")
    razon: NonEmpty
    ids_tvn: tuple[str, ...] = ()
    pasajes_nuevos: tuple[Citation, ...] = ()
    metodo: str = "tvn-snapshot-v2"
    snapshot_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class Group(Schema):
    """News about the same event, ranked in the inbox. Counters are derived from the members."""

    id_grupo: NonEmpty
    titulo: NonEmpty
    tema: TopicOrNone
    miembros: Annotated[tuple[Member, ...], Field(min_length=1)]
    puntaje: Score
    estado_evidencia: EvidenceState
    contexto: tuple[ContextLink, ...]
    sin_contexto_motivo: NonEmpty | None
    id_caso: NonEmpty | None
    sintetico: bool = False
    cobertura_tvn: TVNCoverage | None = None

    @model_validator(mode="after")
    def _members_and_context(self) -> Self:
        if len({m.id_noticia for m in self.miembros}) != len(self.miembros):
            raise ValueError("miembros no puede repetir id_noticia")
        if bool(self.contexto) == (self.sin_contexto_motivo is not None):
            raise ValueError("sin_contexto_motivo se indica si y solo si el grupo no tiene contexto oficial")
        return self

    @property
    def n_noticias(self) -> int:
        return len(self.miembros)

    @property
    def n_medios(self) -> int:
        return len({m.medio for m in self.miembros})

    @property
    def n_procedencias(self) -> int:
        return len({m.procedencia for m in self.miembros})


def sort_inbox(groups: Iterable[Group]) -> list[Group]:
    """§4: highest score first; ties go to the more urgent group, then to the lower id."""
    return sorted(groups, key=lambda g: (-g.puntaje.valor, -g.puntaje.componentes.U, g.id_grupo))


class Answer(Schema):
    """Answer of the query box. Without evidence it abstains and says what information is needed (§8)."""

    id_consulta: NonEmpty
    consulta: NonEmpty
    estado: AnswerState
    respuesta: NonEmpty | None = None
    citas: tuple[Citation, ...] = ()
    motivo_abstencion: NonEmpty | None = None
    faltante: NonEmpty | None = None
    versiones: tuple[ContradictionVersion, ...] = ()
    afirmaciones: tuple[Claim, ...] = ()

    @model_validator(mode="after")
    def _shape_matches_state(self) -> Self:
        if self.afirmaciones:
            if self.estado != "respondida" or self.respuesta != " ".join(claim.texto for claim in self.afirmaciones):
                raise ValueError("la respuesta debe componerse exactamente de sus afirmaciones")
            if len({claim.id_afirmacion for claim in self.afirmaciones}) != len(self.afirmaciones):
                raise ValueError("las afirmaciones de una respuesta necesitan IDs únicos")
            if set(self.citas) != {citation for claim in self.afirmaciones for citation in claim.citas}:
                raise ValueError("las citas de la respuesta deben corresponder a sus afirmaciones")
        if self.estado == "respondida":
            if self.respuesta is None or not self.citas:
                raise ValueError("una respuesta respondida necesita texto y citas")
        elif self.estado == "abstencion":
            if self.respuesta is not None or self.citas:
                raise ValueError("una abstencion no responde ni cita")
            if self.motivo_abstencion is None:
                raise ValueError("una abstencion necesita motivo_abstencion")
            if self.faltante is None:
                raise ValueError("una abstencion necesita faltante: qué información se necesita")
        elif len(self.versiones) < 2:
            raise ValueError("una contradiccion necesita al menos dos versiones")
        return self


class ReviewRecord(Schema):
    """One human decision on a case (§3 stage 7). The history of a case is a list of these."""

    id_caso: NonEmpty
    estado: ReviewState
    responsable: NonEmpty | None
    fecha: UtcDatetime
    nota: NonEmpty | None

    @model_validator(mode="after")
    def _a_person_is_responsible(self) -> Self:
        if self.estado != "nuevo" and self.responsable is None:
            raise ValueError("responsable es obligatorio: la revisión la hace una persona")
        return self


def _history(records: Iterable[ReviewRecord], case_id: str) -> list[ReviewRecord]:
    """Records of one case by date; equal dates keep their order in the file."""
    return sorted((r for r in records if r.id_caso == case_id), key=lambda r: r.fecha)


def current_review_state(records: Iterable[ReviewRecord], case_id: str) -> ReviewState:
    """The state of the latest record by date, or `nuevo` for a case nobody has reviewed."""
    history = _history(records, case_id)
    return history[-1].estado if history else "nuevo"


def transition_errors(records: Iterable[ReviewRecord]) -> list[str]:
    records = list(records)
    errors = []
    for case_id in dict.fromkeys(r.id_caso for r in records):
        previous: ReviewState = "nuevo"
        for index, record in enumerate(_history(records, case_id)):
            if record.estado == "nuevo":
                if index:
                    errors.append(f"{case_id}: transición no permitida {previous} → nuevo")
            elif record.estado not in REVIEW_TRANSITIONS[previous]:
                errors.append(f"{case_id}: transición no permitida {previous} → {record.estado}")
            previous = record.estado
    return errors


# ---------------------------------------------------------------------------------------------------------
# The whole output
# ---------------------------------------------------------------------------------------------------------


class ReviewArchive(Schema):
    """An immutable reviewed snapshot; its decisions never apply to current content."""

    ficha: CaseFile
    grupo: Group
    evidencias: dict[str, Evidence]
    decisiones: tuple[ReviewRecord, ...]
    contenido_sha256: str

    @staticmethod
    def digest(case: CaseFile, group: Group, evidence: dict[str, Evidence]) -> str:
        import hashlib
        import json
        payload = {"case": case.model_dump(mode="json"), "group": group.model_dump(mode="json"),
                   "evidence": {key: value.model_dump(mode="json") for key, value in evidence.items()}}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _bound_decisions(self) -> Self:
        if self.contenido_sha256 != self.digest(self.ficha, self.grupo, self.evidencias):
            raise ValueError("Archived review snapshot hash mismatch")
        if self.ficha.id_grupo != self.grupo.id_grupo or any(r.id_caso != self.ficha.id_caso for r in self.decisiones):
            raise ValueError("Archived review belongs to another case")
        if transition_errors(self.decisiones):
            raise ValueError("Invalid archived review cycle")
        return self


class OutputSet(Schema):
    """Everything the interface and the API read, as one object."""

    grupos: tuple[Group, ...]
    evidencias: dict[str, Evidence]
    fichas: tuple[CaseFile, ...]
    consultas: tuple[Answer, ...]
    revisiones: tuple[ReviewRecord, ...]
    historial_revisiones: tuple[ReviewArchive, ...] = ()
    revisiones_vinculadas: tuple[ReviewArchive, ...] = ()

    def review_state(self, case_id: str) -> ReviewState:
        return current_review_state(self.revisiones, case_id)


#: Evidence of an official figure must say which period and unit it describes (§3 stage 3).
_OFFICIAL_FIELDS = ("periodo", "unidad", "valor")


def verify(output: OutputSet) -> None:
    """Rules no single record can check. Raises `ValueError` listing every problem found."""
    problems: list[str] = []
    evidences = output.evidencias
    groups = {g.id_grupo: g for g in output.grupos}
    case_files = {f.id_caso: f for f in output.fichas}

    citations = [c for f in output.fichas for claim in f.afirmaciones for c in claim.citas]
    citations += [c for answer in output.consultas for c in answer.citas]
    citations += [c for answer in output.consultas for claim in answer.afirmaciones for c in claim.citas]
    problems += citation_errors(citations, evidences)

    versions = [v for f in output.fichas for contradiction in f.contradicciones for v in contradiction.versiones]
    versions += [v for answer in output.consultas for v in answer.versiones]
    problems += citation_errors([citation for version in versions for citation in version.citas], evidences)
    problems += [
        f"{v.id_evidencia}: la versión contradictoria cita una evidencia que no existe"
        for v in versions
        if v.id_evidencia not in evidences
    ]

    for group in output.grupos:
        if group.cobertura_tvn is not None:
            problems += citation_errors(group.cobertura_tvn.pasajes_nuevos, evidences)
            problems += [f"{group.id_grupo}: TVN coverage refers to missing evidence {key}"
                         for key in group.cobertura_tvn.ids_tvn if key not in evidences]
        ids = [m.id_noticia for m in group.miembros] + [link.id_evidencia for link in group.contexto]
        problems += [f"{group.id_grupo}: {i} no está en evidencias" for i in ids if i not in evidences]
        for link in group.contexto:
            evidence = evidences.get(link.id_evidencia)
            if evidence is not None:
                problems += [
                    f"{link.id_evidencia}: la evidencia de contexto oficial no tiene el campo {name!r}"
                    for name in _OFFICIAL_FIELDS
                    if name not in evidence.campos or (name != "valor" and not evidence.campos[name].strip())
                ]
        if group.id_caso is not None and group.id_caso not in case_files:
            problems.append(f"{group.id_grupo}: id_caso {group.id_caso} no tiene ficha")

    for case_file in output.fichas:
        if case_file.borrador is not None:
            if case_file.metodo_generacion == "seleccion-afirmaciones-v1" and case_file.borrador.respaldo is None:
                problems.append(f"{case_file.id_caso}: generated draft is missing accepted claim references")
            from whoami.generation.package_selection import verify_package
            try:
                verify_package(case_file.borrador, case_file.afirmaciones)
            except ValueError as error:
                problems.append(f"{case_file.id_caso}: {error}")
        owner = groups.get(case_file.id_grupo)
        if owner is None:
            problems.append(f"{case_file.id_caso}: el grupo {case_file.id_grupo} no existe")
            continue
        if owner.id_caso != case_file.id_caso:
            problems.append(f"{case_file.id_caso}: el grupo {owner.id_grupo} no la referencia (id_caso={owner.id_caso})")
        own = {m.id_noticia for m in owner.miembros} | {link.id_evidencia for link in owner.contexto}
        problems += [
            f"{case_file.id_caso}: cita {i}, que no pertenece al grupo {owner.id_grupo}"
            for i in case_file.cited_ids
            if i not in own
        ]
        if owner.estado_evidencia != "suficiente_para_borrador" and not case_file.vacios:
            problems.append(
                f"{case_file.id_caso}: la evidencia es {owner.estado_evidencia} y vacios está vacío: debe decir qué falta"
            )

    for record in output.revisiones:
        reviewed = case_files.get(record.id_caso)
        if reviewed is None:
            problems.append(f"{record.id_caso}: hay revisiones de un caso sin ficha")
        elif record.estado == "aprobado_como_borrador":
            source = groups.get(reviewed.id_grupo)
            if source is not None and source.estado_evidencia == "insuficiente":
                problems.append(f"{record.id_caso}: no se puede pasar a aprobado_como_borrador con evidencia insuficiente")
            if reviewed.borrador is None:
                problems.append(f"{record.id_caso}: no se puede pasar a aprobado_como_borrador sin borrador")
    problems += transition_errors(output.revisiones)

    if output.revisiones_vinculadas:
        from whoami.reviews import review_snapshots
        expected = review_snapshots(output)
        seen = set()
        for snapshot in output.revisiones_vinculadas:
            case_id = snapshot.ficha.id_caso
            if case_id in seen or expected.get(case_id) != snapshot:
                problems.append(f"{case_id}: review decisions do not match the current content snapshot")
            seen.add(case_id)
        if seen != set(expected):
            problems.append("Active reviews are missing a content snapshot")

    if problems:
        raise ValueError("el paquete es incoherente:\n- " + "\n- ".join(problems))
