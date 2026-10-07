"""Case files and editorial packages from a group's sources, and the assembly of the whole output.

Two strategies share one contract. `SingleShotGenerator` asks for claims, gaps, action and package in one call.
`TwoStepGenerator` asks for claims only, verifies them in code, and writes the package from the verified claim
texts alone, so nothing the verifier dropped can leak into the draft.
Either way only verified claims reach the case file, and a case with none is not generated.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from whoami.contracts import (
    BRIEF_MAX_WORDS,
    COPY_MAX_WORDS,
    TEXT_SCOPE_DESCRIPTION,
    TEXT_SCOPE_FULL,
    TEXT_SCOPE_HEADLINE,
    EvidenceState,
    TextScope,
)
from whoami.generation.contradictions import ContradictionChecker, RuleBasedChecker
from whoami.generation.jsonschemas import (
    case_file_schema,
    claims_schema,
    package_schema,
    response_format,
    single_shot_schema,
    to_claims,
    to_package,
)
from whoami.generation.entailment import EntailmentChecker
from whoami.generation.prompting import Gate, build_messages
from whoami.generation.query_box import answer_query
from whoami.generation.retrieval import Retriever
from whoami.generation.verifier import VerificationReport, verify_claims
from whoami.llm.client import CapExceeded, LLMError
from whoami.schemas import CaseFile, Claim, EditorialPackage, Evidence, Group, OutputSet, sort_inbox, verify

CLAIMS_TASK = (
    "Extrae las afirmaciones verificables de las fuentes. Cada afirmación lleva tipo "
    "(hecho, declaracion, inferencia o hipotesis), atribuida_a solo si es una declaración, "
    "y al menos una cita literal."
)
PACKAGE_TASK = (
    "Redacta el paquete editorial usando únicamente las afirmaciones verificadas que se te entregan: "
    "titulo, brief (máximo {brief} palabras), enfoque_interes_publico, exactamente 3 preguntas de investigación, "
    "fuentes_y_verificaciones, guion y copy_digital (máximo {copy} palabras). "
    "No agregues hechos, cifras, entrevistas ni citas que no estén en las afirmaciones."
).format(brief=BRIEF_MAX_WORDS, copy=COPY_MAX_WORDS)
SINGLE_SHOT_TASK = (
    f"{CLAIMS_TASK} Indica en vacios qué información falta y en accion_recomendada el siguiente paso. "
    f"{PACKAGE_TASK.replace('que se te entregan', 'que tú mismo extraigas')}"
)
SINGLE_SHOT_NO_DRAFT_TASK = f"{CLAIMS_TASK} Indica en vacios qué información falta y en accion_recomendada el siguiente paso."

UNSUPPORTED_ISSUE = "los pasajes citados no respaldan la afirmación"

DEFAULT_ACTIONS: dict[EvidenceState, str] = {
    "insuficiente": "Buscar más fuentes antes de redactar: la evidencia es insuficiente.",
    "parcial": "Verificar los vacíos con una fuente primaria antes de publicar.",
    "suficiente_para_borrador": "Revisar el borrador y confirmar las cifras con la fuente primaria.",
}
_SCOPE_RICHNESS: tuple[TextScope, ...] = (TEXT_SCOPE_HEADLINE, TEXT_SCOPE_DESCRIPTION, TEXT_SCOPE_FULL)


class NoGroundedClaims(Exception):
    """No claim of the group survived verification: the caller skips the case."""


class CaseGenerator(Protocol):
    def generate(
        self, group: Group, evidences: Mapping[str, Evidence], id_caso: str
    ) -> tuple[CaseFile, VerificationReport, int]: ...


def _describe(error: ValueError) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
    return str(error)


def _retry_task(task: str, error: str) -> str:
    return f"{task}\n\nLa respuesta anterior no cumplió los límites del paquete ({error}). Corrígelo."


@dataclass(frozen=True)
class _Sources:
    """The evidence a group may cite: its members and its official context."""

    evidences: dict[str, Evidence]

    @classmethod
    def of(cls, group: Group, evidences: Mapping[str, Evidence]) -> "_Sources":
        ids = [m.id_noticia for m in group.miembros] + [link.id_evidencia for link in group.contexto]
        return cls({i: evidences[i] for i in ids if i in evidences})

    @property
    def ids(self) -> list[str]:
        return list(self.evidences)


def _text_scope(group: Group) -> TextScope:
    """The richest scope among the members: the draft rests on the best text there is."""
    return max((m.alcance_texto for m in group.miembros), key=_SCOPE_RICHNESS.index)


def _wants_package(group: Group) -> bool:
    return group.estado_evidencia != "insuficiente"


def _gaps(group: Group, stated: Iterable[str], report: VerificationReport, package_error: str | None) -> tuple[str, ...]:
    stated = [gap.strip() for gap in stated if gap.strip()]
    gaps = list(stated)
    gaps += [
        f"afirmación descartada: {UNSUPPORTED_ISSUE} ({claim_id})"
        if reasons == (UNSUPPORTED_ISSUE,)
        else f"afirmación descartada por cita no verificable ({claim_id})"
        for claim_id, reasons in report.issues.items()
    ]
    if package_error is not None:
        gaps.append(f"el borrador no cumplió los límites del paquete editorial y no se generó: {package_error}")
    if group.estado_evidencia != "suficiente_para_borrador" and not stated:
        gaps.append(f"La evidencia es {group.estado_evidencia}: faltan fuentes que respalden el caso.")
    return tuple(gaps)


class _Generator:
    def __init__(
        self,
        llm,
        model: str,
        checker: ContradictionChecker | None = None,
        entailment: EntailmentChecker | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._checker = checker or RuleBasedChecker()
        self._entailment = entailment

    def _complete(self, messages: list[dict], purpose: str, ids: Sequence[str], schema: dict) -> dict:
        completion = self._llm.complete(
            self._model,
            messages,
            purpose=purpose,
            evidence_ids=ids,
            response_format=response_format(purpose, schema),
        )
        data = completion.json()
        if not isinstance(data, dict):
            raise ValueError("el modelo no devolvió un objeto JSON")
        return data

    def _first_call(self, group: Group, call):
        """Runs the call that must produce claims; any failure of the model means there is no case."""
        try:
            return call()
        except CapExceeded:
            raise
        except (LLMError, ValueError) as error:
            raise NoGroundedClaims(f"{group.id_grupo}: el modelo no devolvió afirmaciones válidas") from error

    def _check(self, sources: _Sources, claims: Sequence[Claim]) -> VerificationReport:
        """Citation verification, then the entailment check on the claims that passed it: `no_respaldada` is dropped."""
        report = verify_claims(claims, sources.evidences)
        if self._entailment is None:
            return report
        kept: list[Claim] = []
        issues = dict(report.issues)
        for claim in report.valid_claims:
            if self._entailment.check(claim, sources.evidences) == "no_respaldada":
                issues[claim.id_afirmacion] = (UNSUPPORTED_ISSUE,)
            else:
                kept.append(claim)
        return VerificationReport(tuple(kept), issues, report.repaired)

    def _verify(self, group: Group, sources: _Sources, claims: Sequence[Claim]) -> VerificationReport:
        report = self._check(sources, claims)
        if not report.valid_claims:
            raise NoGroundedClaims(f"{group.id_grupo}: ninguna afirmación pasó la verificación")
        return report

    def _assemble(
        self,
        group: Group,
        evidences: Mapping[str, Evidence],
        id_caso: str,
        report: VerificationReport,
        *,
        stated_gaps: Iterable[str],
        action: str | None,
        package: EditorialPackage | None,
        package_error: str | None,
    ) -> CaseFile:
        return CaseFile(
            id_caso=id_caso,
            id_grupo=group.id_grupo,
            alcance_texto=_text_scope(group),
            afirmaciones=report.valid_claims,
            borrador=package,
            vacios=_gaps(group, stated_gaps, report, package_error),
            contradicciones=self._checker.check(group, evidences),
            accion_recomendada=(action or "").strip() or DEFAULT_ACTIONS[group.estado_evidencia],
            sintetico=group.sintetico,
        )


@dataclass(frozen=True)
class _SingleShotAnswer:
    claims: tuple[Claim, ...]
    gaps: list[str]
    action: str
    package: EditorialPackage | None
    package_error: str | None


class SingleShotGenerator(_Generator):
    """One call: claims, gaps, recommended action and package. A package over the limits gets one retry."""

    def generate(
        self, group: Group, evidences: Mapping[str, Evidence], id_caso: str
    ) -> tuple[CaseFile, VerificationReport, int]:
        sources = _Sources.of(group, evidences)
        wants_package = _wants_package(group)
        task = SINGLE_SHOT_TASK if wants_package else SINGLE_SHOT_NO_DRAFT_TASK
        scope = _text_scope(group)
        answer = self._first_call(group, lambda: self._ask(sources, task, scope, wants_package))
        report = self._verify(group, sources, answer.claims)
        calls = 1
        if wants_package and answer.package_error is not None:
            calls = 2
            try:
                retry = self._ask(sources, _retry_task(task, answer.package_error), scope, wants_package)
                retry_report = self._check(sources, retry.claims)
            except (LLMError, ValueError):
                retry = None
            if retry is not None and retry.package_error is None and retry_report.valid_claims:
                answer, report = retry, retry_report
        case_file = self._assemble(
            group,
            evidences,
            id_caso,
            report,
            stated_gaps=answer.gaps,
            action=answer.action,
            package=answer.package,
            package_error=answer.package_error,
        )
        return case_file, report, calls

    def _ask(self, sources: _Sources, task: str, scope: TextScope, wants_package: bool) -> _SingleShotAnswer:
        schema = single_shot_schema(sources.ids) if wants_package else case_file_schema(sources.ids)
        data = self._complete(build_messages(task, sources.evidences.values()), "ficha", sources.ids, schema)
        package, package_error = None, None
        if wants_package:
            try:
                package = to_package(data.get("borrador"), scope)
            except ValueError as error:
                package_error = _describe(error)
        return _SingleShotAnswer(
            claims=to_claims(data),
            gaps=[g for g in data.get("vacios", []) if isinstance(g, str)],
            action=data.get("accion_recomendada") or "",
            package=package,
            package_error=package_error,
        )


class TwoStepGenerator(_Generator):
    """Call 1: claims. Code verifies them. Call 2: the package, from the verified claim texts only."""

    def generate(
        self, group: Group, evidences: Mapping[str, Evidence], id_caso: str
    ) -> tuple[CaseFile, VerificationReport, int]:
        sources = _Sources.of(group, evidences)
        claims = self._first_call(
            group,
            lambda: to_claims(
                self._complete(
                    build_messages(CLAIMS_TASK, sources.evidences.values()),
                    "afirmaciones",
                    sources.ids,
                    claims_schema(sources.ids),
                )
            ),
        )
        report = self._verify(group, sources, claims)
        calls = 1
        package, package_error = None, None
        if _wants_package(group):
            package, package_error, package_calls = self._write_package(report, _text_scope(group))
            calls += package_calls
        case_file = self._assemble(
            group, evidences, id_caso, report, stated_gaps=(), action=None, package=package, package_error=package_error
        )
        return case_file, report, calls

    def _write_package(
        self, report: VerificationReport, scope: TextScope
    ) -> tuple[EditorialPackage | None, str | None, int]:
        cited_ids = list(dict.fromkeys(c.id_evidencia for claim in report.valid_claims for c in claim.citas))
        task, error = PACKAGE_TASK, None
        for attempt in (1, 2):
            try:
                data = self._complete(
                    build_messages(task, [], claims=report.valid_claims), "paquete", cited_ids, package_schema()
                )
                return to_package(data, scope), None, attempt
            except CapExceeded:
                raise
            except (LLMError, ValueError) as failure:
                error = _describe(failure)
                task = _retry_task(PACKAGE_TASK, error)
        return None, error, 2


# ---------------------------------------------------------------------------------------------------------
# The whole output
# ---------------------------------------------------------------------------------------------------------


def build_outputs(
    output_set_in: OutputSet,
    generator: CaseGenerator,
    query_specs: Iterable[tuple[str, str]],
    *,
    retriever: Retriever,
    gate: Gate,
    llm,
    model: str,
    top_n: int = 5,
    skip_insufficient: bool = False,
) -> OutputSet:
    """Case files for the `top_n` groups of the inbox (not counting `insuficiente` ones when `skip_insufficient`)
    and answers for the queries, validated with `verify`.

    Groups, evidence and the review history come from `output_set_in`; groups without a case file end with
    `id_caso=None` and reviews of cases that were not generated are left out.
    """
    evidences = output_set_in.evidencias
    case_files: list[CaseFile] = []
    inbox = [g for g in sort_inbox(output_set_in.grupos) if not (skip_insufficient and g.estado_evidencia == "insuficiente")]
    for group in inbox[:top_n]:
        id_caso = group.id_caso or f"CASO-{group.id_grupo.removeprefix('G-')}"
        try:
            case_file, _, _ = generator.generate(group, evidences, id_caso)
        except NoGroundedClaims:
            continue
        case_files.append(case_file)

    case_ids = {case_file.id_grupo: case_file.id_caso for case_file in case_files}
    output = OutputSet(
        grupos=tuple(g.model_copy(update={"id_caso": case_ids.get(g.id_grupo)}) for g in output_set_in.grupos),
        evidencias=evidences,
        fichas=tuple(case_files),
        consultas=tuple(
            answer_query(id_consulta, consulta, retriever, gate, evidences, llm, model)
            for id_consulta, consulta in query_specs
        ),
        revisiones=tuple(r for r in output_set_in.revisiones if r.id_caso in case_ids.values()),
    )
    verify(output)
    return output
