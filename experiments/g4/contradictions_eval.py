"""T05: rule-based figure/date conflicts vs an LLM pairwise check, on labeled pairs of real news (plus 3 synthetic).

    uv run python experiments/g4/contradictions_eval.py --model MODEL

Positives: two items that give incompatible figures or dates for the same thing (or the same figure for different
scopes, which a reader must see side by side). Negatives: same-event pairs that agree, and pairs with different
figures that are not in conflict (different places or different events). Labeled by Claude Opus (agent).
"""

import argparse
import json
import sys
from pathlib import Path

from whoami.generation.contradictions import LLMContradictionChecker, RuleBasedChecker
from whoami.schemas import Components, Evidence, Group, Member, Score

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from query_devset import load_evidences  # noqa: E402

POSITIVES = [
    ("N-28b94956af41", "N-2854bda599c2", "denuncias de médicos: más de 80 vs más de 70"),
    ("N-7d75257fb6ae", "N-e77e82298905", "Operación Poseidón: 12 vs 13 aprehendidos"),
    ("N-2cff9136fa14", "N-9bfd18db165c", "crecimiento según Chapman: 6.4 % vs 4.4 % (períodos distintos)"),
    ("N-d18285de0b4f", "N-64434241b521", "tránsitos del Canal: 32 hasta diciembre vs 33 desde el 15 de octubre"),
    ("N-a5a999ae57d4", "N-ccd682251e95", "influenza: dos muertes vs 63 (alcances distintos)"),
    ("N-syn000000001", "N-syn000000002", "sintético: pasajeros del Metro 9 vs 11 millones"),
    ("N-syn000000003", "N-syn000000004", "sintético: reapertura del puente 12 vs 20 de octubre"),
    ("N-syn000000005", "N-syn000000006", "sintético: familias damnificadas 15 vs 40"),
]
NEGATIVE_PAIR_IDS = [0, 25, 88, 163, 112, 233, 34, 57, 208, 38, 200, 185, 168, 132, 174, 292, 304, 255]


def as_group(first: Evidence, second: Evidence) -> Group:
    members = tuple(
        Member(id_noticia=e.id_evidencia, titulo=e.titulo, url=e.url, medio=e.campos.get("medio", "medio"),
               procedencia=f"{e.campos.get('medio', 'medio')}-{n}", fecha_publicacion=e.fecha or "2026-10-01T00:00:00Z",
               alcance_texto="titular_descripcion" if "descripcion" in e.campos else "titular_metadatos", recirculada_en=None)
        for n, e in enumerate((first, second))
    )
    score = Score.from_components(Components(R=0, I=0, U=0, N=0, E=0), {k: "experimento" for k in "RIUNE"})
    return Group(id_grupo="G-exp", titulo=first.titulo, tema="sin_tema", miembros=members, puntaje=score,
                 estado_evidencia="parcial", contexto=(), sin_contexto_motivo="experimento", id_caso=None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemma-4-26b-a4b-it")
    args = parser.parse_args()
    from whoami.llm import default_llm

    evidences = load_evidences()
    gold = {json.loads(l)["p"]: json.loads(l) for l in (HERE / "pares_mismo_evento.jsonl").open(encoding="utf-8")}
    cases = [(a, b, True, why) for a, b, why in POSITIVES]
    cases += [(gold[p]["id_a"], gold[p]["id_b"], False, f"par {p} (etiqueta {gold[p]['etiqueta']})") for p in NEGATIVE_PAIR_IDS]
    rule, llm = RuleBasedChecker(), LLMContradictionChecker(default_llm(), args.model)
    rows = []
    for a, b, positive, why in cases:
        group = as_group(evidences[a], evidences[b])
        rows.append({"a": a, "b": b, "positivo": positive, "nota": why,
                     "reglas": bool(rule.check(group, evidences)), "llm": bool(llm.check(group, evidences)),
                     "titulos": [evidences[a].titulo[:90], evidences[b].titulo[:90]]})
    out = HERE / "resultados" / f"contradicciones_{args.model}.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    for name in ("reglas", "llm"):
        tp = sum(r[name] and r["positivo"] for r in rows); fp = sum(r[name] and not r["positivo"] for r in rows)
        fn = sum(not r[name] and r["positivo"] for r in rows)
        print(f"{args.model} {name:6s} detecta {tp}/{tp + fn} positivos, falsas alarmas {fp}/{sum(not r['positivo'] for r in rows)}")


if __name__ == "__main__":
    main()
