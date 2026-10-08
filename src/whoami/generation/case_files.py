"""Case files and editorial packages from a group's sources, and the assembly of the whole output.

`TwoStepGenerator` asks for claims only, verifies them in code, and writes the package from the verified claim
texts alone, so nothing the verifier dropped can leak into the draft.
Only verified claims reach the case file, and a case with none is not generated.
"""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import islice
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
from whoami.generation.entailment import EntailmentChecker
from whoami.generation.jsonschemas import claims_schema, package_selection_schema, response_format, to_claims
from whoami.generation.package_selection import compose_package
from whoami.generation.prompting import CosineGate, build_messages, complete_json
from whoami.generation.query_box import answer_query
from whoami.generation.retrieval import Retriever
from whoami.generation.verifier import VerificationReport, verify_claims
from whoami.pipeline.tvn_coverage import assess_legacy_groups
from whoami.reviews import bind_reviews, review_snapshots
from whoami.llm.client import CapExceeded, LLMError
from whoami.schemas import CaseFile, Claim, EditorialPackage, Evidence, Group, OutputSet, ReviewArchive, sort_inbox, verify

#: Room for claims plus a full package; the cap stops a model that degenerates into endless output.
GENERATION_MAX_TOKENS = 2000

CLAIMS_TASK = (
    "Extrae las afirmaciones verificables de las fuentes. Cada afirmación lleva tipo "
    "(hecho, declaracion, inferencia o hipotesis), atribuida_a solo si es una declaración, "
    "y al menos una cita literal."
)
PACKAGE_TASK = (
    "Organiza un paquete editorial usando únicamente los IDs de las afirmaciones verificadas. "
    "titulo: un ID cuya afirmación informe de forma clara y atractiva. "
    "brief, guion, copy_digital: listas ordenadas de IDs, sin repetir. "
    "El código conserva sus textos, tipos y atribución; no escribas prosa ni nuevas afirmaciones. "
    "Elige un enfoque: verificacion, impacto o seguimiento, y tres preguntas distintas entre "
    "fuentes, vacios, actualizaciones, periodo e impacto. "
    "Selecciona textos breves: el brief no supera {brief} palabras y el copy {copy}."
).format(brief=BRIEF_MAX_WORDS, copy=COPY_MAX_WORDS)

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


def _gaps(group: Group, report: VerificationReport, package_error: str | None) -> tuple[str, ...]:
    gaps = [
        f"afirmación descartada: {UNSUPPORTED_ISSUE} ({claim_id})"
        if reasons == (UNSUPPORTED_ISSUE,)
        else f"afirmación descartada por cita no verificable ({claim_id})"
        for claim_id, reasons in report.issues.items()
    ]
    if package_error is not None:
        gaps.append(f"el borrador no cumplió los límites del paquete editorial y no se generó: {package_error}")
    if group.estado_evidencia != "suficiente_para_borrador":
        gaps.append(f"La evidencia es {group.estado_evidencia}: faltan fuentes que respalden el caso.")
    return tuple(gaps)


class TwoStepGenerator:
    """Call 1: claims. Code verifies them. Call 2: the package, from the verified claim texts only."""

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

    def generate(
        self, group: Group, evidences: Mapping[str, Evidence], id_caso: str
    ) -> tuple[CaseFile, VerificationReport, int]:
        sources = _Sources.of(group, evidences)
        claims = self._extract_claims(group, sources)
        report = self._verify(group, sources, claims)
        calls = 1
        package, package_error = None, None
        if _wants_package(group):
            package, package_error, package_calls = self._write_package(report, _text_scope(group))
            calls += package_calls
        case_file = CaseFile(
            id_caso=id_caso,
            id_grupo=group.id_grupo,
            alcance_texto=_text_scope(group),
            afirmaciones=report.valid_claims,
            borrador=package,
            vacios=_gaps(group, report, package_error),
            contradicciones=self._checker.check(group, evidences),
            accion_recomendada=DEFAULT_ACTIONS[group.estado_evidencia],
            sintetico=group.sintetico,
            metodo_generacion="seleccion-afirmaciones-v1",
        )
        return case_file, report, calls

    def _complete(self, messages: list[dict], purpose: str, ids: Sequence[str], schema: dict) -> dict:
        data = complete_json(
            self._llm,
            self._model,
            messages,
            purpose=purpose,
            evidence_ids=ids,
            response_format=response_format(purpose, schema),
            max_tokens=GENERATION_MAX_TOKENS,
        )
        if not isinstance(data, dict):
            raise ValueError("el modelo no devolvió un objeto JSON")
        return data

    def _extract_claims(self, group: Group, sources: _Sources) -> tuple[Claim, ...]:
        """Any failure of the model means there is no case."""
        try:
            return to_claims(
                self._complete(
                    build_messages(CLAIMS_TASK, sources.evidences.values()),
                    "afirmaciones",
                    sources.ids,
                    claims_schema(sources.ids),
                )
            )
        except CapExceeded:
            raise
        except (LLMError, ValueError) as error:
            raise NoGroundedClaims(f"{group.id_grupo}: el modelo no devolvió afirmaciones válidas") from error

    def _verify(self, group: Group, sources: _Sources, claims: Sequence[Claim]) -> VerificationReport:
        """Citation verification, then the entailment check on the claims that passed it: `no_respaldada` is dropped."""
        report = verify_claims(claims, sources.evidences)
        if self._entailment is not None:
            kept: list[Claim] = []
            issues = dict(report.issues)
            for claim in report.valid_claims:
                if self._entailment.check(claim, sources.evidences) == "no_respaldada":
                    issues[claim.id_afirmacion] = (UNSUPPORTED_ISSUE,)
                else:
                    kept.append(claim)
            report = VerificationReport(tuple(kept), issues, report.repaired)
        if not report.valid_claims:
            raise NoGroundedClaims(f"{group.id_grupo}: ninguna afirmación pasó la verificación")
        return report

    def _write_package(
        self, report: VerificationReport, scope: TextScope
    ) -> tuple[EditorialPackage | None, str | None, int]:
        cited_ids = list(dict.fromkeys(c.id_evidencia for claim in report.valid_claims for c in claim.citas))
        task, error = PACKAGE_TASK, None
        for attempt in (1, 2):
            try:
                data = self._complete(
                    build_messages(task, [], claims=report.valid_claims), "paquete", cited_ids,
                    package_selection_schema([claim.id_afirmacion for claim in report.valid_claims])
                )
                return compose_package(data, report.valid_claims, scope), None, attempt
            except CapExceeded:
                raise
            except (LLMError, ValueError) as failure:
                error = _describe(failure)
                task = _retry_task(PACKAGE_TASK, error)
        return None, error, 2


# ---------------------------------------------------------------------------------------------------------
# One group and the whole output
# ---------------------------------------------------------------------------------------------------------


def generate_case_file(generator: CaseGenerator, group: Group, evidences: Mapping[str, Evidence]) -> CaseFile:
    """The case file of one group, through the same generator and verification as the batch.

    Raises `NoGroundedClaims` when no claim of the group survives verification."""
    id_caso = group.id_caso or f"CASO-{group.id_grupo.removeprefix('G-')}"
    case_file, _, _ = generator.generate(group, evidences, id_caso)
    return case_file


def _case_files(generator: CaseGenerator, groups: Iterable[Group], evidences: Mapping[str, Evidence]) -> Iterator[CaseFile]:
    """Lazily, so a caller that needs only the first few case files stops calling the model."""
    for group in groups:
        try:
            yield generate_case_file(generator, group, evidences)
        except NoGroundedClaims:
            continue


def select_case_groups(groups: Iterable[Group], top_n: int, skip_insufficient: bool) -> tuple[list[Group], list[Group]]:
    """The inbox groups that take a case-file slot, and the fallback candidates in rank order.

    Topics TVN already covered take no slot. With `skip_insufficient`, `insuficiente` groups take none either, and
    the fallback is the insufficient groups regardless of coverage: abstention is the point of that case file."""
    inbox = sort_inbox(groups)
    novel = [g for g in inbox if g.cobertura_tvn.estado != "cubierto"]
    if not skip_insufficient:
        return novel[:top_n], []
    return [g for g in novel if g.estado_evidencia != "insuficiente"][:top_n], [g for g in inbox if g.estado_evidencia == "insuficiente"]


def build_outputs(
    output_set_in: OutputSet,
    generator: CaseGenerator,
    query_specs: Iterable[tuple[str, str]],
    *,
    retriever: Retriever,
    gate: CosineGate,
    llm,
    model: str,
    top_n: int = 5,
    skip_insufficient: bool = False,
) -> OutputSet:
    """Case files for the `top_n` groups of the inbox and answers for the queries, validated with `verify`.

    Topics TVN covered are skipped. With `skip_insufficient`, `insuficiente` groups take no slot of the top, but the best
    one that yields a case file is added, covered or not: the output keeps a case without enough evidence (challenge requirement).

    Groups, evidence and the review history come from `output_set_in`; groups without a case file end with
    `id_caso=None` and reviews of cases that were not generated are left out.
    """
    evidences = output_set_in.evidencias
    assessed = assess_legacy_groups(output_set_in.grupos, evidences)
    top, fallback = select_case_groups(assessed, top_n, skip_insufficient)
    case_files = [*_case_files(generator, top, evidences), *islice(_case_files(generator, fallback, evidences), 1)]

    case_ids = {case_file.id_grupo: case_file.id_caso for case_file in case_files}
    regenerated = {case.id_caso: case for case in case_files}
    groups = tuple(g.model_copy(update={"id_caso": case_ids.get(g.id_grupo)}) for g in assessed)
    bindings = {snapshot.ficha.id_caso: snapshot for snapshot in output_set_in.revisiones_vinculadas}
    legacy = output_set_in.model_copy(update={"revisiones": tuple(r for r in output_set_in.revisiones if r.id_caso not in bindings)})
    previous = review_snapshots(legacy)
    archives = list(output_set_in.historial_revisiones)
    active_reviews = []
    for case_id in dict.fromkeys(r.id_caso for r in output_set_in.revisiones):
        reviews = tuple(r for r in output_set_in.revisiones if r.id_caso == case_id)
        old = bindings[case_id] if case_id in bindings else previous[case_id]
        if case_id in regenerated and case_id in bindings:
            candidate = OutputSet(grupos=groups, evidencias=evidences, fichas=tuple(case_files),
                                  consultas=(), revisiones=reviews)
            if old == review_snapshots(candidate)[case_id]:
                active_reviews.extend(reviews)
                continue
        if old not in archives:
            archives.append(old)
    output = OutputSet(
        grupos=groups,
        evidencias=evidences,
        fichas=tuple(case_files),
        consultas=tuple(
            answer_query(id_consulta, consulta, retriever, gate, evidences, llm, model)
            for id_consulta, consulta in query_specs
        ),
        revisiones=tuple(active_reviews), historial_revisiones=tuple(archives),
    )
    verify(output)
    return bind_reviews(output)
