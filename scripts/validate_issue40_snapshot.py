"""Run the corrected offline pipeline on current news without replacing historical outputs.

Reuse pinned-model vectors only for byte-identical document text in the verified
frozen corpus; encode new/changed text locally. No provider or held-out access.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from whoami import store
from whoami.backend.pipeline import load_pipeline
from whoami.backend.repository import EditorialRepository
from whoami.backend.service import EditorialService
from whoami.contracts import NEWS_CSV, PROCESSED
from whoami.embeddings import Embedder, MODEL_NAME, document_text, embed_corpus
from whoami.evaluation.tasks import SeededEmbedder, aligned_vectors
from whoami.pipeline.ai import ai_components
from whoami.pipeline.evidence import load_news_rows
from whoami.pipeline.run import default_vectors_path, run
from whoami.pipeline.tvn_coverage import COVERAGE_METHOD, is_tvn
from whoami.schemas import Evidence, verify


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    vectors_choice = parser.add_mutually_exclusive_group(required=True)
    vectors_choice.add_argument("--vectors-output", type=Path)
    vectors_choice.add_argument("--reuse-capture", type=Path, help="Reuse vectors only if CSV, model identity and vector hash match a prior capture")
    args = parser.parse_args()
    if args.output.exists() or (args.vectors_output and args.vectors_output.exists()):
        parser.error("Choose new output directories; historical validation runs are never replaced")
    frozen = {row["id_evidencia"]: Evidence.model_validate(row)
              for row in store.read_jsonl(PROCESSED / "evidencias.jsonl")}
    frozen_path = default_vectors_path()
    ids, vectors = aligned_vectors(frozen_path, frozen)
    rows = load_news_rows()
    local = Embedder()
    seeded = SeededEmbedder(local, ids, vectors, frozen)
    reused = sum(document_text(row) in seeded.news for row in rows)
    print(f"Current dated news: {len(rows)}; identical frozen texts: {reused}; texts absent from frozen vectors: {len(rows) - reused}", flush=True)
    if args.reuse_capture:
        previous = json.loads((args.reuse_capture / "metrics.json").read_text(encoding="utf-8"))
        new_vectors = Path(previous["new_vectors_manifest"]).parent / f"{MODEL_NAME}.npy"
        if (previous["current_news_csv_sha256"] != sha256(NEWS_CSV)
                or previous["encoder_identity"] != local.cache_identity
                or previous["new_vectors_sha256"] != sha256(new_vectors)):
            parser.error("Prior capture does not match current news, model or vector bytes")
    else:
        new_vectors = embed_corpus(rows, seeded, args.vectors_output)
    output = run(new_vectors, data=args.output / "data", outputs=args.output / "outputs",
                 configure=ai_components(None, "gemini-3.5-flash-lite"))
    verify(output)
    restored = store.load(args.output / "data", args.output / "outputs")
    assert restored == output
    repository = EditorialRepository(args.output / "editorial.sqlite3")
    repository.import_bundle(load_pipeline(args.output / "data", args.output / "outputs"))
    service = EditorialService(repository)
    inbox = service.inbox()
    assert not any(all(is_tvn(member) for member in group["miembros"]) for group in inbox)
    assert all(group["cobertura_tvn"]["estado"] != "cubierto" for group in inbox)
    report = {
        "mode": "current G1 news, local pinned embeddings, offline production AI configuration",
        "current_news_csv_sha256": sha256(NEWS_CSV),
        "frozen_evidence_sha256": sha256(PROCESSED / "evidencias.jsonl"),
        "frozen_vectors_sha256": sha256(frozen_path),
        "new_vectors_sha256": sha256(new_vectors),
        "new_vectors_manifest": str(new_vectors.parent / "manifest.json"),
        "encoder_identity": local.cache_identity,
        "dated_news": len(rows), "frozen_texts_reused": reused, "texts_not_in_frozen_corpus": len(rows) - reused,
        "texts_encoded_locally": 0 if args.reuse_capture else len(rows) - reused,
        "vectors_reused_from_capture": str(args.reuse_capture) if args.reuse_capture else None,
        "coverage_method": COVERAGE_METHOD,
        "groups": len(output.grupos), "coverage": dict(Counter(group.cobertura_tvn.estado for group in output.grupos)),
        "inbox_groups": len(inbox), "tvn_only_inbox_groups": 0,
        "top_five": [{key: group[key] for key in ("id_grupo", "titulo", "puntaje", "cobertura_tvn")} for group in inbox[:5]],
        "verified": True, "round_trip_verified": True, "network_calls": 0, "held_out_read": False,
        "limitations": ["Coverage refers to the loaded TVN snapshot, not every publication on the web.",
                        "Topic labels remain machine-proposed; these artifacts do not measure editorial appeal.",
                        "22 undated current news rows remain in the source CSV and outside grouping.",
                        "No new generative model output or human support evaluation in this offline pipeline run."],
    }
    (args.output / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("dated_news", "groups", "coverage", "inbox_groups")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
