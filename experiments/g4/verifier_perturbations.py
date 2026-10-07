"""Controlled test of the two verifiers: true claims from demo case files and perturbed copies of them.

    uv run python experiments/g4/verifier_perturbations.py --model MODEL
"""

import argparse
import json
from pathlib import Path

from whoami.generation.verifier import check_claim
from whoami.schemas import Citation, Claim
from whoami.store import load_demo

HERE = Path(__file__).parent
# (claim text, type, author, citations as (id, field, passage)), then its perturbation and the kind of perturbation.
CASES = [
    (("La Autoridad del Canal de Panamá limitará a 32 los tránsitos diarios a partir del 12 de octubre.", "declaracion", "Autoridad del Canal de Panamá", [("N-2cf673d2b74a", "descripcion", "limitará a 32 los tránsitos diarios a partir del 12 de octubre")]),
     "La Autoridad del Canal de Panamá limitará a 34 los tránsitos diarios a partir del 12 de octubre.", "cifra"),
    (("La reducción de tránsitos del Canal se debe a la falta de lluvias.", "hecho", None, [("N-7d665f7db893", "descripcion", "El Canal de Panamá reducirá los tránsitos diarios de buques por la falta de lluvias")]),
     "La reducción de tránsitos del Canal se debe a la falta de lluvias, según confirmó el presidente Mulino.", "atribucion_inventada"),
    (("El motivo que señala el comunicado es el bajo nivel del lago Gatún.", "hecho", None, [("N-2cf673d2b74a", "titulo", "bajo nivel del lago Gatún")]),
     "El motivo que señala el comunicado es la contaminación del lago Gatún.", "causa_inventada"),
    (("Las exportaciones de bienes y servicios fueron 44,36 % del PIB en 2024.", "hecho", None, [("WB-PAN-NE.EXP.GNFS.ZS-2024", "valor", "44,36")]),
     "Las exportaciones de bienes y servicios fueron 44,36 % del PIB en 2024 y crecieron frente a 2023.", "detalle_inventado"),
    (("Analistas citados por TVN ubican la inflación anual de septiembre en 1,1 %.", "declaracion", "analistas citados por TVN", [("N-ff2911fe7429", "descripcion", "Analistas citan una inflación anual de 1,1 % en septiembre")]),
     "Analistas citados por TVN ubican la inflación anual de septiembre en 1,4 %.", "cifra"),
    (("Un informe privado ubica la inflación anual en 2,3 % en septiembre.", "declaracion", "informe privado citado por Metro Libre", [("N-dce13ea37725", "descripcion", "Un informe privado ubica la inflación anual en 2,3 % en septiembre")]),
     "El Banco Central ubica la inflación anual en 2,3 % en septiembre.", "atribucion_inventada"),
    (("El IDAAN realizará un corte programado de agua en San Miguelito el 9 de octubre.", "hecho", None, [("N-2491ad97ee36", "titulo", "Corte programado de agua en San Miguelito el 9 de octubre")]),
     "El IDAAN realizará un corte programado de agua en Arraiján el 9 de octubre.", "lugar_inventado"),
    (("El corte de agua está programado de 8:00 a. m. a 4:00 p. m.", "hecho", None, [("N-2491ad97ee36", "descripcion", "de 8:00 a. m. a 4:00 p. m.")]),
     "El corte de agua está programado de 8:00 a. m. a 6:00 p. m.", "cifra"),
    (("La suspensión del servicio se debe a trabajos en la planta potabilizadora.", "hecho", None, [("N-b212eb58ea29", "descripcion", "por trabajos en la planta potabilizadora")]),
     "La suspensión del servicio se debe a una avería grave en la planta potabilizadora.", "causa_inventada"),
    (("La ministra de Comercio anunció un nuevo reglamento para permisos de construcción.", "hecho", None, [("N-e0d7e73e44fc", "titulo", "anuncia nuevo reglamento para permisos de construcción")]),
     "La ministra de Comercio anunció un nuevo reglamento que elimina los permisos de construcción.", "detalle_inventado"),
    (("Un sismo de magnitud 5,6 ocurrió a 148 km al sur-sureste de Burica, Panamá, el 17 de diciembre de 2025.", "hecho", None, [("USGS-us6000rvkl", "lugar", "148 km SSE of Burica, Panama")]),
     "Un sismo de magnitud 5,6 en la zona fronteriza con Costa Rica dejó daños en viviendas de Burica.", "detalle_inventado"),
    (("Un sismo de magnitud 5,6 ocurrió frente a Burica el 17 de diciembre de 2025.", "hecho", None, [("USGS-us6000rvkl", "valor", "5,6")]),
     "Un sismo de magnitud 6,1 ocurrió frente a Burica el 17 de diciembre de 2025.", "cifra"),
]


def claims():
    evidences = load_demo().evidencias
    out = []
    for n, ((text, kind, author, cites), perturbed, how) in enumerate(CASES, 1):
        citations = tuple(Citation(id_evidencia=i, campo=f, pasaje=p) for i, f, p in cites)
        out.append(("verdadera", "-", Claim(id_afirmacion=f"V-{n}", texto=text, tipo=kind, citas=citations, atribuida_a=author)))
        out.append(("perturbada", how, Claim(id_afirmacion=f"P-{n}", texto=perturbed, tipo=kind, citas=citations, atribuida_a=author)))
    return out, evidences


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemma-4-26b-a4b-it")
    args = parser.parse_args()
    import sys

    sys.path.insert(0, str(HERE))
    from case_files_devset import entailment
    from whoami.llm import default_llm

    llm = default_llm()
    items, evidences = claims()
    rows = []
    for label, how, claim in items:
        det = check_claim(claim, evidences)
        verdict = entailment(llm, args.model, claim, evidences)
        rows.append({"id": claim.id_afirmacion, "etiqueta": label, "perturbacion": how, "determinista_rechaza": bool(det.issues),
                     "motivos": list(det.issues), "implicacion": verdict})
    out = HERE / "resultados" / f"verificadores_{args.model}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    true = [r for r in rows if r["etiqueta"] == "verdadera"]
    bad = [r for r in rows if r["etiqueta"] == "perturbada"]
    llm_rejects = lambda r: r["implicacion"] == "no_respaldada"
    both = lambda r: r["determinista_rechaza"] or llm_rejects(r)
    for name, rule in (("determinista", lambda r: r["determinista_rechaza"]), ("implicación LLM", llm_rejects), ("ambos", both)):
        print(f"{args.model} {name:16s} detecta {sum(map(rule, bad))}/{len(bad)} perturbadas; rechaza por error {sum(map(rule, true))}/{len(true)} verdaderas")
    print("por tipo:", {r["id"]: (r["perturbacion"], r["determinista_rechaza"], r["implicacion"]) for r in bad})


if __name__ == "__main__":
    main()
