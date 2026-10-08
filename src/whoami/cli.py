"""`whoami` command line.

    whoami ingest [--only tvn,usgs,inec]     download feeds and APIs to data/raw (network)
    whoami build                        data/raw to data/processed (offline)
    whoami refresh                      ingest + build
    whoami demo                         write the synthetic contract set to data/demo (offline)
    whoami generar [--modelo M] [--top N] [--consultas PATH] [--sin-implicacion]
                                        case files and answers to outputs/ (calls the LLM): two-step generator,
                                        hybrid retriever, cosine gate; the entailment check is on unless --sin-implicacion
    whoami embed                        embed noticias.csv with the local model to data/processed/embeddings (offline)
    whoami pipeline [--vectors PATH] [--sin-llm] [--modelo-llm MODEL]
                                        news + embeddings to data/processed/grupos.jsonl and evidencias.jsonl;
                                        --sin-llm makes it fully offline (logistic topics, embedding-only grouping)
    whoami export-backend               export persisted case files and human reviews (offline)
    whoami evaluar                     G7 benchmark, baselines, metrics and automated tests
"""

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from whoami import demo
from whoami.embeddings import Embedder, embed_corpus
from whoami.generation import run
from whoami.ingest import inec, manifest, usgs, worldbank
from whoami.ingest.news import build as news_build
from whoami.ingest.news import ingest as news_ingest
from whoami.ingest.news.sources import SOURCES
from whoami.llm import LLMError, default_llm
from whoami.pipeline import run as pipeline
from whoami.pipeline.ai import CountingLLM, ai_components
from whoami.pipeline.evidence import load_news_rows
from whoami.pipeline.report import format_summary
from whoami.pipeline.topics import DEFAULT_LLM_MODEL


@dataclass(frozen=True)
class Dataset:
    keys: frozenset[str]
    ingest: Callable[[set[str] | None], list[str]]
    build: Callable[[], dict]


#: Adding a dataset is one line here.
DATASETS = {
    "news": Dataset(frozenset({"gdelt", "gdelt-gkg", *(source.key for source in SOURCES)}), news_ingest.ingest, news_build.build),
    "worldbank": Dataset(frozenset({"worldbank"}), lambda _: worldbank.fetch(), worldbank.build),
    "usgs": Dataset(frozenset({"usgs"}), lambda _: usgs.fetch(), usgs.build),
    "inec": Dataset(frozenset({"inec"}), lambda _: inec.fetch(), inec.build),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whoami", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("ingest", "refresh"):
        command = commands.add_parser(name)
        command.add_argument("--only", help="comma-separated keys: news sources, worldbank, usgs, inec")
    commands.add_parser("build")
    commands.add_parser("demo")
    commands.add_parser("embed")
    pipeline_command = commands.add_parser("pipeline")
    pipeline_command.add_argument(
        "--vectors", type=Path, help="embeddings .npy next to a manifest.json with their ids (default: the only one)"
    )
    pipeline_command.add_argument("--sin-llm", action="store_true", help="no LLM at all: logistic topics, embeddings-only grouping")
    pipeline_command.add_argument("--modelo-llm", default=DEFAULT_LLM_MODEL, help="chat model for topics and same-event verdicts")
    run.add_arguments(commands.add_parser("generar"))
    from whoami.evaluation import run as evaluation

    evaluation.add_arguments(commands.add_parser("evaluar"))

    export_command = commands.add_parser("export-backend")
    export_command.add_argument("--database", type=Path, help="SQLite database; defaults to WHOAMI_DATABASE")
    export_command.add_argument("--output", type=Path, default=Path("outputs"), help="delivery directory")
    args = parser.parse_args(argv)

    if args.command == "evaluar":
        try:
            return evaluation.main(args)
        except (ValueError, FileNotFoundError, KeyError) as error:
            parser.error(str(error))

    if args.command == "generar":
        return run.main(args)

    if args.command == "demo":
        output = demo.generate()
        print(f"data/demo: {len(output.grupos)} grupos, {len(output.fichas)} fichas, {len(output.consultas)} consultas")
        return 0

    if args.command == "embed":
        path = embed_corpus(load_news_rows(), Embedder(), pipeline.EMBEDDINGS_DIR)
        print(f"{path}: vectores y manifest.json escritos")
        return 0

    if args.command == "pipeline":
        try:
            llm = None if args.sin_llm else CountingLLM(default_llm())
        except KeyError as error:
            parser.error(f"falta la variable de entorno {error.args[0]}: define la clave o corre con --sin-llm")
        try:
            output = pipeline.run(args.vectors, configure=ai_components(llm, args.modelo_llm))
        except (pipeline.PipelineInputError, LLMError) as error:
            parser.error(str(error))
        print(format_summary(output, llm.counts() if llm else None))
        return 0

    if args.command == "export-backend":
        from whoami.backend.export import export_backend
        from whoami.backend.repository import EditorialRepository
        from whoami.backend.settings import Settings

        database = args.database or Settings.from_environment().database
        if not database.is_file():
            parser.error(f"backend database does not exist: {database}")
        print(json.dumps(export_backend(EditorialRepository(database), args.output), indent=2))
        return 0

    only = set(args.only.split(",")) if getattr(args, "only", None) else None
    known = set().union(*(dataset.keys for dataset in DATASETS.values()))
    if only and only - known:
        parser.error(f"unknown --only keys: {', '.join(sorted(only - known))}")

    failures = []
    if args.command in ("ingest", "refresh"):
        for dataset in DATASETS.values():
            selected = only & dataset.keys if only else None
            if selected != set():
                failures += dataset.ingest(selected)
    if args.command in ("build", "refresh"):
        reports = {name: dataset.build() for name, dataset in DATASETS.items()}
        reports["manifest"] = manifest.build()
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
