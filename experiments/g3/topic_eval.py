"""Topic classification bake-off on the 300-item gold set.

    uv run --all-groups python experiments/g3/topic_eval.py [model ...]

Needs `vectors/` and `dvectors/` for each model (see README). The keyword baseline is the packaged
`whoami.pipeline.topics_keywords.classify_keywords`.
"""
import json, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from corpus import DATA, HERE, rows, text
from whoami.pipeline.topics_keywords import classify_keywords

TOPICS = ["economia","logistica_canal","turismo","servicios_publicos","eventos_naturales","regulacion","sin_tema"]
r = rows(); idx = {x["id_noticia"]: i for i, x in enumerate(r)}
gold = [json.loads(l) for l in (DATA / "topic_gold.jsonl").open()]
gi = np.array([idx[g["id_noticia"]] for g in gold]); y = np.array([g["tema"] for g in gold])
gemma = {json.loads(l)["id_noticia"]: json.loads(l) for l in (DATA / "topic_pred_gemma.jsonl").open()}
gemma_pred = np.array([gemma[g["id_noticia"]]["tema"] for g in gold])

def f1(pred): return round(f1_score(y, pred, labels=TOPICS, average="macro", zero_division=0), 3)
def f1_six(pred): return round(f1_score(y, pred, labels=TOPICS[:6], average="macro", zero_division=0), 3)

results = {}
kw_ours = np.array([topic for topic, _, _ in classify_keywords([text(r[i]) for i in gi])])
kw_orig = np.where(kw_ours == "sin_tema", "economia", kw_ours)  # the original baseline defaulted to economy
results["palabras_clave (original, sin coincidencia -> economía)"] = (f1(kw_orig), f1_six(kw_orig), 0)
results["palabras_clave (sin coincidencia -> sin_tema)"] = (f1(kw_ours), f1_six(kw_ours), 0)
results["gemma por titular"] = (f1(gemma_pred), f1_six(gemma_pred), 300)

dlabels = np.array(json.load((HERE / "dvectors/labels.json").open()))
skf = StratifiedKFold(5, shuffle=True, random_state=0)
best = {}
for model in sys.argv[1:] or ["minilm","mpnet","potion_m2v","jina_v2_es","e5_small","e5_large","gemma300m","qwen3_06b_q","jina_v3"]:
    X = np.load(HERE / "vectors" / f"{model}.npy")[gi]
    D = np.load(HERE / "dvectors" / f"{model}.npy")
    zs = dlabels[np.argmax(X @ D.T, axis=1)]
    results[f"zero-shot descripciones [{model}]"] = (f1(zs), f1_six(zs), 0)
    cent = np.empty(len(y), dtype=object); lr = np.empty(len(y), dtype=object); lr_margin = np.zeros(len(y))
    for tr, te in skf.split(X, y):
        C = np.stack([X[tr][y[tr] == t].mean(0) for t in TOPICS]); C /= np.linalg.norm(C, axis=1, keepdims=True)
        cent[te] = np.array(TOPICS)[np.argmax(X[te] @ C.T, axis=1)]
        clf = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced").fit(X[tr], y[tr])
        proba = clf.predict_proba(X[te]); order = np.sort(proba, axis=1)
        lr[te] = clf.classes_[np.argmax(proba, axis=1)]; lr_margin[te] = order[:, -1] - order[:, -2]
    results[f"centroide (CV 5) [{model}]"] = (f1(cent), f1_six(cent), 0)
    results[f"regresión logística (CV 5) [{model}]"] = (f1(lr), f1_six(lr), 0)
    for thr in (0.2, 0.35, 0.5):
        hyb = np.where(lr_margin >= thr, lr, gemma_pred)
        results[f"híbrido logística+gemma margen<{thr} [{model}]"] = (f1(hyb), f1_six(hyb), int((lr_margin < thr).sum()))

for name, (a, b, calls) in sorted(results.items(), key=lambda kv: -kv[1][0]):
    print(f"{a:.3f}  {b:.3f}  llm={calls:3d}  {name}")
