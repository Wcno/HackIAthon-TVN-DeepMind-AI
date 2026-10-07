"""G4 case-file experiments: single-shot vs two-step generation, deterministic vs deterministic + LLM entailment.

    uv run python experiments/g4/case_files_devset.py --generator single|two --model MODEL [--data demo|DIR] [--groups N] [--entailment]

Writes `resultados/fichas_<data>_<generator>_<model>.jsonl` with every case file, its verification report and,
with `--entailment`, one verdict per kept claim. Live calls go through the shared LLM layer (cached, ledgered, capped).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from whoami.generation.case_files import NoGroundedClaims, SingleShotGenerator, TwoStepGenerator
from whoami.generation.jsonschemas import entailment_schema, response_format
from whoami.generation.prompting import build_messages, leaks_canary
from whoami.llm import InvalidJSON, LLMError
from whoami.schemas import sort_inbox
from whoami.generation.run import load_input
from whoami.store import load_demo

HERE = Path(__file__).parent
ENTAILMENT_TASK = (
    "Decide si los pasajes citados respaldan la afirmación. respaldada: todo lo que afirma está en los pasajes; "
    "parcial: una parte no está; no_respaldada: los pasajes no la sostienen o la contradicen. "
    "Una inferencia o hipótesis está respaldada si se presenta como tal y se apoya en los pasajes."
)


def entailment(llm, model: str, claim, evidences) -> str:
    cited = {c.id_evidencia: evidences[c.id_evidencia] for c in claim.citas if c.id_evidencia in evidences}
    passages = "\n".join(f"- {c.id_evidencia} [{c.campo}]: {c.pasaje}" for c in claim.citas)
    messages = build_messages(
        ENTAILMENT_TASK + f"\nPasajes citados:\n{passages}",
        cited.values(),
        user_query=f"Afirmación ({claim.tipo}): {claim.texto}",
    )
    try:
        data = llm.complete(
            model, messages, purpose="g4-implicacion", evidence_ids=list(cited),
            response_format=response_format("implicacion", entailment_schema()), max_tokens=200,
        ).json()
        return data["veredicto"]
    except (InvalidJSON, LLMError, KeyError):
        return "error"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", choices=["single", "two"], default="two")
    parser.add_argument("--model", default="gemma-4-26b-a4b-it")
    parser.add_argument("--data", default="demo")
    parser.add_argument("--groups", type=int, default=10)
    parser.add_argument("--entailment", action="store_true")
    args = parser.parse_args()

    from whoami.llm import default_llm

    llm = default_llm()
    output = load_demo() if args.data == "demo" else load_input(Path(args.data), Path(args.data))
    generator = (SingleShotGenerator if args.generator == "single" else TwoStepGenerator)(llm, args.model)
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
        verdicts = [entailment(llm, args.model, c, output.evidencias) for c in case_file.afirmaciones] if args.entailment else []
        totals.update(Counter(f"implicacion_{v}" for v in verdicts))
        totals["calls"] += len(verdicts)
        text = json.dumps(case_file.model_dump(mode="json"), ensure_ascii=False)
        totals["canario"] += leaks_canary(text)
        records.append({
            "id_grupo": group.id_grupo, "titulo": group.titulo, "estado_evidencia": group.estado_evidencia,
            "ficha": case_file.model_dump(mode="json"), "descartadas": {k: list(v) for k, v in report.issues.items()},
            "reparadas": len(report.repaired), "implicacion": verdicts,
        })
    out = HERE / "resultados" / f"fichas_{Path(args.data).name}_{args.generator}_{args.model}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    print(f"{args.generator} {args.model} {args.data}: {dict(totals)}")


if __name__ == "__main__":
    main()
