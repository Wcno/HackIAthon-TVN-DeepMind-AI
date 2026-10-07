"""`whoami generar`: case files and query answers from the processed groups and evidence, written as the output set.

The model and the embedder are arguments of `generar`, so the whole run is testable with fakes; only `main`
builds the real ones.
"""

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from whoami.contracts import DATA, EVIDENCE_FILE, GROUPS_FILE, OUTPUTS, PROCESSED, REVIEWS_FILE
from whoami.generation.case_files import (
    CaseGenerator,
    NoGroundedClaims,
    SingleShotGenerator,
    TwoStepGenerator,
    build_outputs,
)
from whoami.generation.entailment import EntailmentChecker
from whoami.generation.evidence_index import Embedder, LocalEmbedder, default_retrievers
from whoami.generation.prompting import CosineGate
from whoami.generation.verifier import VerificationReport
from whoami.llm import default_llm
from whoami.schemas import CaseFile, Evidence, Group, OutputSet
from whoami.store import read_jsonl, write

DEFAULT_QUERIES = DATA / "consultas_demo.jsonl"
DEFAULT_MODEL = "gemma-4-26b-a4b-it"
VECTORS_FILE = "evidencias_vectores.npy"
GENERATORS = {"single": SingleShotGenerator, "two": TwoStepGenerator}
RETRIEVERS = ("bm25", "emb", "hybrid")


@dataclass(frozen=True)
class RunConfig:
    generador: str
    modelo: str
    top: int
    recuperador: str
    consultas: Path
    implicacion: bool


def add_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--generador", choices=GENERATORS, default="two")
    command.add_argument("--modelo", default=DEFAULT_MODEL)
    command.add_argument("--top", type=int, default=10, help="groups to generate a case file for (insufficient ones are skipped)")
    command.add_argument("--recuperador", choices=RETRIEVERS, default="hybrid")
    command.add_argument("--consultas", type=Path, default=DEFAULT_QUERIES, help="JSONL with id and consulta")
    command.add_argument("--implicacion", action="store_true", help="check every kept claim is supported by its passages")


def config_from(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        args.generador, args.modelo, args.top, args.recuperador, args.consultas, args.implicacion
    )


class CountingLLM:
    """Delegates to the real model and counts successful calls by purpose and cache outcome."""

    def __init__(self, llm) -> None:
        self._llm = llm
        self.calls: Counter[tuple[str, str]] = Counter()

    def complete(self, model: str, messages: list[dict], *, purpose: str, **options):
        completion = self._llm.complete(model, messages, purpose=purpose, **options)
        self.calls[(purpose, "hit" if completion.cached else "miss")] += 1
        return completion

    def by_purpose(self) -> dict[str, dict[str, int]]:
        purposes = sorted({purpose for purpose, _ in self.calls})
        return {p: {"hit": self.calls[(p, "hit")], "miss": self.calls[(p, "miss")]} for p in purposes}


class RecordingGenerator:
    """Delegates to a generator and tallies what verification kept and dropped."""

    def __init__(self, generator: CaseGenerator) -> None:
        self._generator = generator
        self.kept = 0
        self.dropped = 0
        self.skipped_cases = 0

    def generate(
        self, group: Group, evidences: dict[str, Evidence], id_caso: str
    ) -> tuple[CaseFile, VerificationReport, int]:
        try:
            result = self._generator.generate(group, evidences, id_caso)
        except NoGroundedClaims:
            self.skipped_cases += 1
            raise
        _, report, _ = result
        self.kept += len(report.valid_claims)
        self.dropped += len(report.issues)
        return result


@dataclass(frozen=True)
class Summary:
    fichas: int
    casos_omitidos: int
    afirmaciones_conservadas: int
    afirmaciones_descartadas: int
    paquetes: int
    respuestas: dict[str, int]
    llamadas: dict[str, dict[str, int]] = field(default_factory=dict)

    def render(self) -> str:
        lines = [
            f"fichas: {self.fichas} (sin afirmaciones verificables: {self.casos_omitidos})",
            f"afirmaciones: {self.afirmaciones_conservadas} conservadas, {self.afirmaciones_descartadas} descartadas",
            f"paquetes editoriales: {self.paquetes}",
            "respuestas: " + (", ".join(f"{state}: {n}" for state, n in sorted(self.respuestas.items())) or "ninguna"),
            "llamadas al modelo (aciertos de caché / fallos):",
        ]
        lines += [f"  {purpose}: {c['hit']} / {c['miss']}" for purpose, c in self.llamadas.items()]
        return "\n".join(lines)


def load_queries(path: Path) -> list[tuple[str, str]]:
    return [(record["id"], record["consulta"]) for record in read_jsonl(path)]


def load_input(data: Path, outputs: Path) -> OutputSet:
    """Groups and evidence from `data`; the review history from `outputs` if it exists. No case files yet, so the
    set is not verified here: `build_outputs` verifies the result, after dropping reviews of cases not generated."""
    reviews = outputs / REVIEWS_FILE
    return OutputSet.model_validate(
        {
            "grupos": read_jsonl(data / GROUPS_FILE),
            "evidencias": {record["id_evidencia"]: record for record in read_jsonl(data / EVIDENCE_FILE)},
            "fichas": [],
            "consultas": [],
            "revisiones": read_jsonl(reviews) if reviews.exists() else [],
        }
    )


def generar(config: RunConfig, llm, embedder: Embedder, data: Path, outputs: Path) -> Summary:
    """Builds the case files and answers, validates them and writes them to `data` and `outputs`."""
    source = load_input(data, outputs)
    counting = CountingLLM(llm)
    retrievers = default_retrievers(source.evidencias.values(), embedder, data / VECTORS_FILE)
    entailment = EntailmentChecker(counting, config.modelo) if config.implicacion else None
    generator = RecordingGenerator(GENERATORS[config.generador](counting, config.modelo, entailment=entailment))
    output = build_outputs(
        source,
        generator,
        load_queries(config.consultas),
        retriever=retrievers[config.recuperador],
        gate=CosineGate(retrievers["emb"]),
        llm=counting,
        model=config.modelo,
        top_n=config.top,
        skip_insufficient=True,
    )
    write(output, data, outputs)
    return Summary(
        fichas=len(output.fichas),
        casos_omitidos=generator.skipped_cases,
        afirmaciones_conservadas=generator.kept,
        afirmaciones_descartadas=generator.dropped,
        paquetes=sum(f.borrador is not None for f in output.fichas),
        respuestas=dict(Counter(answer.estado for answer in output.consultas)),
        llamadas=counting.by_purpose(),
    )


def main(args: argparse.Namespace) -> int:
    summary = generar(config_from(args), default_llm(), LocalEmbedder(), PROCESSED, OUTPUTS)
    print(summary.render())
    return 0
