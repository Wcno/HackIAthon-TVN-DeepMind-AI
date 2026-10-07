"""`whoami` command line.

    whoami ingest [--only tvn,usgs,inec]     download feeds and APIs to data/raw (network)
    whoami build                        data/raw to data/processed (offline)
    whoami refresh                      ingest + build
    whoami demo                         write the synthetic contract set to data/demo (offline)
    whoami generar [--generador single|two] [--modelo M] [--top N] [--recuperador bm25|emb|hybrid]
                   [--compuerta coseno|llm|ambas] [--consultas PATH] [--implicacion]
                                        case files and answers to outputs/ (calls the LLM)
"""

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass

from whoami import demo
from whoami.generation import run
from whoami.ingest import inec, manifest, usgs, worldbank
from whoami.ingest.news import build as news_build
from whoami.ingest.news import ingest as news_ingest
from whoami.ingest.news.sources import SOURCES


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


def main() -> int:
    parser = argparse.ArgumentParser(prog="whoami", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("ingest", "refresh"):
        command = commands.add_parser(name)
        command.add_argument("--only", help="comma-separated keys: news sources, worldbank, usgs, inec")
    commands.add_parser("build")
    commands.add_parser("demo")
    run.add_arguments(commands.add_parser("generar"))
    args = parser.parse_args()

    if args.command == "generar":
        return run.main(args)

    if args.command == "demo":
        output = demo.generate()
        print(f"data/demo: {len(output.grupos)} grupos, {len(output.fichas)} fichas, {len(output.consultas)} consultas")
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
