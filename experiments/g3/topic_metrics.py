"""Macro F1 of a topic prediction file against `datos/topic_gold.jsonl`.

    uv run --all-groups python experiments/g3/topic_metrics.py <pred.jsonl>
"""
import json, sys
from pathlib import Path
from sklearn.metrics import f1_score, classification_report
TOPICS = ["economia","logistica_canal","turismo","servicios_publicos","eventos_naturales","regulacion","sin_tema"]
GOLD = Path(__file__).parent / "datos" / "topic_gold.jsonl"

def report(pred_path, gold_path=GOLD, show=False):
    gold = {json.loads(l)["id_noticia"]: json.loads(l)["tema"] for l in open(gold_path)}
    pred = {json.loads(l)["id_noticia"]: json.loads(l)["tema"] for l in open(pred_path)}
    ids = [i for i in gold if i in pred]
    y, p = [gold[i] for i in ids], [pred[i] for i in ids]
    six = TOPICS[:6]
    out = {"n": len(ids), "macro_f1_7": round(f1_score(y, p, labels=TOPICS, average="macro", zero_division=0), 3),
           "macro_f1_6": round(f1_score(y, p, labels=six, average="macro", zero_division=0), 3),
           "accuracy": round(sum(a == b for a, b in zip(y, p)) / len(ids), 3)}
    if show: print(classification_report(y, p, labels=TOPICS, zero_division=0))
    return out
if __name__ == "__main__":
    print(report(sys.argv[1], show=True))
