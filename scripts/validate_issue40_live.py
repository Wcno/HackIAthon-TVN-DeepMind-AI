"""Capture bounded real-provider editorial generation on a separately validated snapshot."""

import argparse
import json
import time
from pathlib import Path

from whoami import store
from whoami.generation.case_files import NoGroundedClaims, TwoStepGenerator
from whoami.generation.entailment import EntailmentChecker
from whoami.generation.run import DEFAULT_MODEL, CountingLLM
from whoami.llm import default_llm
from whoami.schemas import OutputSet, sort_inbox, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=2, choices=(1, 2))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; previous captures are never replaced")
    source = store.load(args.snapshot / "data", args.snapshot / "outputs")
    candidates = [group for group in sort_inbox(source.grupos)
                  if group.cobertura_tvn.estado != "cubierto" and group.estado_evidencia != "insuficiente"][:args.cases]
    if len(candidates) != args.cases:
        parser.error("Snapshot has insufficient eligible external groups for the requested capture")
    llm = CountingLLM(default_llm())
    generator = TwoStepGenerator(llm, DEFAULT_MODEL, entailment=EntailmentChecker(llm, DEFAULT_MODEL))
    args.output.mkdir(parents=True)
    cases, results = [], []
    for group in candidates:
        print(f"Generating {group.id_grupo}", flush=True)
        started = time.perf_counter()
        case_id = f"CASO-{group.id_grupo.removeprefix('G-')}"
        try:
            case, report, calls = generator.generate(group, source.evidencias, case_id)
            package = OutputSet(grupos=(group.model_copy(update={"id_caso": case_id}),),
                                evidencias=source.evidencias, fichas=(case,), consultas=(), revisiones=())
            verify(package)
            cases.append(case.model_dump(mode="json"))
            results.append({"group": group.id_grupo, "claims": len(case.afirmaciones),
                            "discarded_claims": len(report.issues), "draft": case.borrador is not None,
                            "claim_references": case.borrador.respaldo if case.borrador else None,
                            "generation_steps_without_entailment": calls, "elapsed_s": time.perf_counter() - started,
                            "verified": True, "review_state": package.review_state(case_id)})
        except NoGroundedClaims:
            results.append({"group": group.id_grupo, "error": "no verified claims", "verified": False})
        store.write_jsonl(args.output / "fichas.jsonl", cases)
    report = {"model": DEFAULT_MODEL, "results": results, "llm_calls_including_entailment": llm.by_purpose(), "held_out_read": False,
              "human_reviews_requested": 0, "complete": len(cases) == args.cases and all(result.get("draft") for result in results),
              "limitations": "This proves provider/protocol execution and mechanical references, not human semantic support or headline appeal."}
    (args.output / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
