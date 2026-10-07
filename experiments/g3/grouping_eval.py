"""Duplicate grouping bake-off (T02) on labeled pairs: pairwise P/R/F1 of 'same event'.

    uv run --all-groups python experiments/g3/grouping_eval.py

Needs `vectors/<model>.npy` for each model listed below (see README); writes `datos/grouping_results.json`.
"""
import json, re, unicodedata
from datetime import datetime
import numpy as np
from sklearn.cluster import AgglomerativeClustering, HDBSCAN
from corpus import DATA, HERE, rows

r = rows(); n = len(r)
pairs = [json.loads(l) for l in (DATA / "pairs_gold.jsonl").open()]
hours = np.array([datetime.fromisoformat(x["fecha_publicacion"].replace("Z", "+00:00")).timestamp() / 3600 for x in r])
WINDOW_H = 72

def fold(s): return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
STOP = set("el la los las de del en y a un una por para con que se su al es lo como mas sus tras sobre ante este esta hoy".split())
def entities(x):
    t = x["titulo"] + " " + x["descripcion"]
    caps = {fold(w) for w in re.findall(r"(?<![.!?¡¿]\s)(?<!^)\b[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+", t) if fold(w) not in STOP}
    nums = set(re.findall(r"\d+(?:[.,]\d+)?", t))
    return caps, nums
ENT = [entities(x) for x in r]

def overlap_bonus(i, j):
    ci, ni = ENT[i]; cj, nj = ENT[j]
    ent = len(ci & cj) / max(1, len(ci | cj))
    num_conflict = bool(ni and nj and not (ni & nj))
    return 0.08 * ent - (0.04 if num_conflict else 0.0)

def score(labels_same, include_story=False):
    tp = fp = fn = tn = 0
    for p in pairs:
        if p["etiqueta"] == 1 and not include_story: continue
        gold = p["etiqueta"] >= (1 if include_story else 2)
        pred = labels_same(p["i"], p["j"])
        tp += gold and pred; fp += (not gold) and pred; fn += gold and not pred; tn += (not gold) and not pred
    prec = tp / (tp + fp) if tp + fp else 0; rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    return round(prec, 3), round(rec, 3), round(f1, 3)

def union_find(sim, thr):
    close = np.abs(hours[:, None] - hours[None, :]) <= WINDOW_H
    parent = list(range(n))
    def find(a):
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    I, J = np.nonzero(np.triu((sim >= thr) & close, 1))
    for a, b in zip(I, J): parent[find(a)] = find(b)
    return np.array([find(a) for a in range(n)])

def report(name, labels):
    same = lambda i, j: labels[i] == labels[j]
    sizes = np.bincount(np.unique(labels, return_inverse=True)[1])
    strict = score(same); loose = score(same, include_story=True)
    return (strict[2], name, strict, loose, int((sizes > 1).sum()), int(sizes.max()))

out = []
for model in ["gemma300m", "jina_v3", "e5_large", "jina_v2_es", "minilm", "potion_m2v", "qwen3_06b_q"]:
    v = np.load(HERE / "vectors" / f"{model}.npy"); sim = v @ v.T
    sims = sorted(sim[p["i"], p["j"]] for p in pairs)
    for thr in np.round(np.arange(0.70, 0.96, 0.025), 3):
        out.append(report(f"{model} umbral {thr} + ventana 72h", union_find(sim, thr)))
    if model in ("gemma300m", "jina_v3", "minilm"):
        bonus = np.zeros_like(sim)
        for a in range(n):
            ca, na = ENT[a]
            for b in np.nonzero(sim[a] > 0.6)[0]:
                bonus[a, b] = overlap_bonus(a, b)
        for thr in np.round(np.arange(0.75, 0.96, 0.025), 3):
            out.append(report(f"{model} umbral {thr} + ventana + entidades/cifras", union_find(sim + bonus, thr)))
        dist = 1 - sim
        far = np.abs(hours[:, None] - hours[None, :]) > WINDOW_H
        dist = np.where(far, 2.0, dist); np.fill_diagonal(dist, 0)
        for t in (0.1, 0.15, 0.2, 0.25, 0.3):
            lab = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average", distance_threshold=t).fit_predict(dist)
            out.append(report(f"{model} aglomerativo promedio d<{t} + ventana", lab))
        for mcs in (2, 3):
            lab = HDBSCAN(min_cluster_size=mcs, metric="precomputed", cluster_selection_epsilon=0.0).fit_predict(np.clip(dist, 0, 2))
            lab = np.where(lab < 0, -np.arange(1, n + 1), lab)
            out.append(report(f"{model} HDBSCAN min_cluster={mcs} + ventana", lab))
out.sort(key=lambda x: -x[0])
print("F1_estricto  nombre  (P,R,F1 estricto)  (P,R,F1 laxo)  grupos>1  mayor")
for f1, name, strict, loose, ng, big in out[:30]:
    print(f"{f1:.3f}  {name:55s} {strict} {loose} {ng} {big}")
json.dump([dict(name=o[1], strict=o[2], loose=o[3], groups=o[4], largest=o[5]) for o in out], (DATA / "grouping_results.json").open("w"), ensure_ascii=False, indent=0)
