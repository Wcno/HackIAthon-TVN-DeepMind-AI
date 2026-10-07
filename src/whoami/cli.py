"""`whoami` command line.

    whoami ingest [--only tvn,usgs,inec]     download feeds and APIs to data/raw (network)
    whoami build                        data/raw to data/processed (offline)
    whoami refresh                      ingest + build
    whoami demo                         write the synthetic contract set to data/demo (offline)
    whoami embed                        embed noticias.csv with the local model to data/processed/embeddings (offline)
    whoami pipeline [--vectors PATH]    news + embeddings to data/processed/grupos.jsonl and evidencias.jsonl (offline)
"""

import argparse
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from whoami import demo
from whoami.embeddings import Embedder, embed_corpus
from whoami.ingest import inec, manifest, usgs, worldbank
from whoami.ingest.news import build as news_build
from whoami.ingest.news import ingest as news_ingest
from whoami.ingest.news.sources import SOURCES
from whoami.pipeline import run as pipeline
from whoami.pipeline.evidence import load_news_rows


@dataclass(frozen=True)
class Dataset:
    keys: frozenset[str]
    ingest: Callable[[set[str] | None], list[str]]
    build: Callable[[], dict]


#: Adding a dataset is one line here.
DATASETS = {
    "news": Dataset(frozenset(source.key for source in SOURCES), news_ingest.ingest, news_build.build),
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
    args = parser.parse_args(argv)

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
            output = pipeline.run(args.vectors)
        except pipeline.PipelineInputError as error:
            parser.error(str(error))
        ranges = Counter(group.puntaje.rango for group in output.grupos)
        print(f"data/processed: {len(output.grupos)} grupos ({dict(ranges)}), {len(output.evidencias)} evidencias")
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
