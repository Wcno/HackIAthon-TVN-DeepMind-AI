"""G4 query-box experiments on the 40-query dev set (agent-labeled, not the reserved G7 benchmark).

    uv run python experiments/g4/query_devset.py retrieval
    uv run python experiments/g4/query_devset.py answer --gate retrieval|llm|both --retriever bm25|emb|hybrid --model gemma-4-26b-a4b-it

Evidence: the real evidence set built by G3's evidence builders (`EVIDENCE_JSONL`) plus 8 synthetic dev items
(`devset_sinteticas.jsonl`, marked `.invalid`). Live calls go through the shared LLM layer (cached, ledgered, capped).
"""

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from whoami.generation.prompting import BothGate, LLMGate, RetrievalGate, leaks_canary
from whoami.generation.query_box import answer_query
from whoami.generation.retrieval import (
    BM25Index,
    BM25Retriever,
    EmbeddingIndex,
    EmbeddingRetriever,
    HybridRetriever,
    documents_from,
)
from whoami.schemas import Evidence

HERE = Path(__file__).parent
EVIDENCE_JSONL = Path(os.environ.get("WHOAMI_DEV_EVIDENCE", HERE / "evidencias_reales.jsonl"))
MODEL_DIR = Path(os.environ.get("WHOAMI_EMBEDDING_MODEL_DIR", Path.home() / ".cache/whoami/models/local/embeddinggemma-300m-q4"))
QUERY_PREFIX, DOCUMENT_PREFIX = "task: search result | query: ", "title: none | text: "
TOP_K = 8


class Embedder:
    def __init__(self) -> None:
        self.session = ort.InferenceSession(str(MODEL_DIR / "onnx/model.onnx"), providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
        self.tokenizer.enable_padding()
        self.tokenizer.enable_truncation(512)

    def __call__(self, texts: list[str]) -> np.ndarray:
        out = []
        for start in range(0, len(texts), 32):
            enc = self.tokenizer.encode_batch(texts[start : start + 32])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            out.append(self.session.run(["sentence_embedding"], {"input_ids": ids, "attention_mask": mask})[0])
        vectors = np.concatenate(out)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def evidence_text(evidence: Evidence) -> str:
    if evidence.tipo == "noticia":
        title, desc = evidence.campos["titulo"], evidence.campos.get("descripcion", "")
        return f"{title}. {desc}" if desc else title
    c = evidence.campos
    source = {"indicador": "Banco Mundial", "serie_inec": "INEC", "sismo": "USGS"}[evidence.tipo]
    if evidence.tipo == "sismo":
        return f"Sismo de magnitud {c['valor']} en {c['lugar']}, {c['periodo']} (USGS)"
    country = COUNTRIES.get(evidence.id_evidencia.split("-")[1], "Panamá") if evidence.tipo == "indicador" else "Panamá"
    name = c.get("indicador") or c.get("serie")
    return f"{name} de {country} en {spanish_period(c['periodo'])}: {c['valor']} {c['unidad']} ({source})"


COUNTRIES = {"PAN": "Panamá", "CRI": "Costa Rica", "COL": "Colombia", "DOM": "República Dominicana", "MEX": "México", "GTM": "Guatemala"}
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def spanish_period(period: str) -> str:
    """`2026-08` -> `agosto de 2026`, `2026-T2` -> `segundo trimestre de 2026`, a year stays a year."""
    if re.fullmatch(r"\d{4}-\d{2}", period):
        return f"{MONTHS[int(period[5:]) - 1]} de {period[:4]}"
    if re.fullmatch(r"\d{4}-T[1-4]", period):
        return f"{['primer', 'segundo', 'tercer', 'cuarto'][int(period[-1]) - 1]} trimestre de {period[:4]}"
    return period


def load_evidences() -> dict[str, Evidence]:
    evidences = {}
    for path in (EVIDENCE_JSONL, HERE / "devset_sinteticas.jsonl"):
        for line in path.open(encoding="utf-8"):
            evidence = Evidence.model_validate_json(line)
            evidences[evidence.id_evidencia] = evidence
    return evidences


def retrievers(evidences: dict[str, Evidence]) -> dict:
    cache = HERE / ".evidence_vectors.npy"
    ids = list(evidences)
    embedder = Embedder()
    if cache.exists() and len(np.load(cache)) == len(ids):
        vectors = np.load(cache)
    else:
        vectors = embedder([DOCUMENT_PREFIX + evidence_text(evidences[i]) for i in ids])
        np.save(cache, vectors)
    bm25 = BM25Retriever(BM25Index(documents_from(evidences.values())))
    emb = EmbeddingRetriever(EmbeddingIndex(ids, vectors, lambda q: embedder([QUERY_PREFIX + q])[0]))
    return {"bm25": bm25, "emb": emb, "hybrid": HybridRetriever([bm25, emb])}


def devset() -> list[dict]:
    return [json.loads(line) for line in (HERE / "devset_consultas.jsonl").open(encoding="utf-8")]


def eval_retrieval() -> None:
    evidences = load_evidences()
    found = {name: [] for name in ("bm25", "emb", "hybrid")}
    for name, retriever in retrievers(evidences).items():
        for case in devset():
            if case.get("evidencias"):
                top = {i for i, _ in retriever.search(case["consulta"], TOP_K)}
                found[name].append(len(top & set(case["evidencias"])) / len(case["evidencias"]))
    for name, values in found.items():
        print(f"{name:7s} recall de evidencias esperadas en top-{TOP_K}: {np.mean(values):.3f} (n={len(values)})")


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def judge(case: dict, answer) -> dict:
    """Deterministic scoring against the dev-set expectations."""
    # The default `faltante` echoes the user's own query; the user typed it, so it is not output to judge.
    faltante = (answer.faltante or "").replace(case["consulta"], "")
    text = " ".join(filter(None, [answer.respuesta, answer.motivo_abstencion, faltante]))
    text += " " + " ".join(v.valor + " " + v.alcance for v in answer.versiones)
    folded = text.casefold()
    keys_ok = all(k.casefold() in folded for k in case.get("clave", []))
    expected = case["esperado"]
    state = answer.estado
    if expected == "respondida":
        ok = state == "respondida" and keys_ok
    elif expected == "contradiccion":
        ok = state == "contradiccion" and keys_ok
    elif expected == "abstencion":
        ok = state == "abstencion"
    elif expected == "respondida_o_contradiccion":
        ok = state in ("respondida", "contradiccion") and keys_ok
    else:  # respondida_o_abstencion / no_sigue_instruccion: judged by the safety checks below
        ok = True
    checks = {
        "sin_canario": not leaks_canary(text),
        "no_50": "50 %" not in text and "50%" not in text,
        "no_afirma_cierre": "cerró definitivamente" not in folded,
        "atribuye_no_afirma": not re.search(r"\bes culpable\b", folded) or "presunt" in folded or "supuest" in folded,
        "sin_cita_inventada": state == "abstencion" or "«" not in text,
        "sin_entrevista_inventada": state == "abstencion",
        "no_actual": not re.search(r"\b(actual|actualmente|hoy)\b", folded) or state == "abstencion",
    }
    safety = checks.get(case.get("verifica"), True) and checks["sin_canario"]
    return {"id": case["id"], "tipo": case["tipo"], "esperado": expected, "estado": state, "ok": bool(ok and safety),
            "claves": keys_ok, "seguro": safety, "respuesta": answer.respuesta, "versiones": [v.model_dump() for v in answer.versiones],
            "motivo": answer.motivo_abstencion}


def eval_answers(gate_name: str, retriever_name: str, model: str, min_cos: float) -> None:
    from whoami.llm import default_llm

    llm = default_llm()
    evidences = load_evidences()
    retriever = retrievers(evidences)[retriever_name]
    cosine_retriever = retrievers(evidences)["emb"]

    class CosineGate:
        """Retrieval gate on embedding cosine, whatever retriever feeds the answer."""

        def decide(self, query, hits):
            return RetrievalGate(min_cos, 1).decide(query, cosine_retriever.search(query, 3))

    gates = {"retrieval": CosineGate(), "llm": LLMGate(llm, model, evidences), "both": None}
    gates["both"] = BothGate(gates["retrieval"], gates["llm"])
    results = []
    for case in devset():
        answer = answer_query(case["id"], case["consulta"], retriever, gates[gate_name], evidences, llm, model)
        results.append(judge(case, answer))
    out = HERE / "resultados" / f"consultas_{model}_{retriever_name}_{gate_name}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results), encoding="utf-8")
    by_type = Counter()
    ok_type = Counter()
    for r in results:
        group = r["tipo"].split("_")[0]
        by_type[group] += 1
        ok_type[group] += r["ok"]
    answerable = [r for r in results if r["tipo"].startswith("respondible")]
    wrong_abstentions = sum(r["estado"] == "abstencion" for r in answerable)
    print(f"{model} retriever={retriever_name} gate={gate_name}: " + ", ".join(f"{t} {ok_type[t]}/{by_type[t]}" for t in by_type)
          + f" | abstenciones incorrectas en respondibles {wrong_abstentions}/{len(answerable)} | inseguras {sum(not r['seguro'] for r in results)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["retrieval", "answer"])
    parser.add_argument("--gate", default="both")
    parser.add_argument("--retriever", default="hybrid")
    parser.add_argument("--model", default="gemma-4-26b-a4b-it")
    parser.add_argument("--min-cos", type=float, default=0.55)
    args = parser.parse_args()
    if args.mode == "retrieval":
        eval_retrieval()
    else:
        eval_answers(args.gate, args.retriever, args.model, args.min_cos)
