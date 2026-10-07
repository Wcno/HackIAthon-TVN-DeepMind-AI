"""G4 case-file experiment: the two-step generator, with or without a post-hoc LLM entailment verdict per kept claim.

    uv run --all-groups python experiments/g4/case_files_devset.py --model MODEL [--data demo|DIR] [--groups N] [--entailment]

Writes `resultados/fichas_<data>_two_<model>.jsonl` with every case file, its verification report and,
with `--entailment`, one verdict per kept claim. Live calls go through the shared LLM layer (cached, ledgered, capped).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from whoami.generation.case_files import NoGroundedClaims, TwoStepGenerator
from whoami.generation.entailment import EntailmentChecker
from whoami.generation.prompting import leaks_canary
from whoami.generation.run import load_input
from whoami.llm import default_llm
from whoami.schemas import sort_inbox
from whoami.store import load_demo

HERE = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--data", default="demo")
    parser.add_argument("--groups", type=int, default=10)
    parser.add_argument("--entailment", action="store_true")
    args = parser.parse_args()

    llm = default_llm()
    output = load_demo() if args.data == "demo" else load_input(Path(args.data), Path(args.data))
    generator = TwoStepGenerator(llm, args.model)
    entailment = EntailmentChecker(llm, args.model)
    groups = [g for g in sort_inbox(output.grupos) if g.estado_evidencia != "insuficiente"][: args.groups]

    records, totals = [], Counter()
    for group in groups:
        try:
            case_file, report, calls = generator.generate(group, output.evidencias, f"CASO-{group.id_grupo[2:]}")
        except NoGroundedClaims as error:
            totals["sin_afirmaciones"] += 1
            records.append({"id_grupo": group.id_grupo, "error": str(error)})
            continue
        dropped = len(report.issues)
        kept = len(report.valid_claims)
        totals.update(calls=calls, fichas=1, afirmaciones=kept + dropped, conservadas=kept, descartadas=dropped,
                      reparadas=len(report.repaired), paquetes=case_file.borrador is not None)
        totals.update(Counter(f"tipo_{c.tipo}" for c in case_file.afirmaciones))
        verdicts = [entailment.check(c, output.evidencias) for c in case_file.afirmaciones] if args.entailment else []
        totals.update(Counter(f"implicacion_{v}" for v in verdicts))
        totals["calls"] += len(verdicts)
        text = json.dumps(case_file.model_dump(mode="json"), ensure_ascii=False)
        totals["canario"] += leaks_canary(text)
        records.append({
            "id_grupo": group.id_grupo, "titulo": group.titulo, "estado_evidencia": group.estado_evidencia,
            "ficha": case_file.model_dump(mode="json"), "descartadas": {k: list(v) for k, v in report.issues.items()},
            "reparadas": len(report.repaired), "implicacion": verdicts,
        })
    out = HERE / "resultados" / f"fichas_{Path(args.data).name}_two_{args.model}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    print(f"two-step {args.model} {args.data}: {dict(totals)}")


if __name__ == "__main__":
    main()
