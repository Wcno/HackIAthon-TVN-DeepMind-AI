"""One model per process: embed the corpus, then report time and peak RSS as JSON.

    uv run --all-groups python experiments/g3/embed_corpus.py <model> corpus|query

Needs the candidate model files under ~/.cache/whoami/models (see `embedders.py`); writes `vectors/<model>.npy`.
"""
import json, resource, sys, time
import numpy as np
from corpus import HERE, rows, text
from embedders import load

key, mode = sys.argv[1], sys.argv[2]  # mode: corpus | query
t0 = time.perf_counter(); embed = load(key); t_load = time.perf_counter() - t0
out = {"model": key, "mode": mode, "load_s": round(t_load, 2)}
if mode == "corpus":
    texts = [text(r) for r in rows()]
    t0 = time.perf_counter(); v = embed(texts, False); out["embed_s"] = round(time.perf_counter() - t0, 2)
    out["dim"] = int(v.shape[1]); out["n"] = int(v.shape[0])
    (HERE / "vectors").mkdir(exist_ok=True)
    np.save(HERE / "vectors" / f"{key}.npy", v)
else:
    t0 = time.perf_counter(); embed(["inflación y precios de alimentos"], True); out["q1_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    t0 = time.perf_counter(); embed(["Canal de Panamá tránsitos y sequía"], True); out["q2_ms"] = round((time.perf_counter() - t0) * 1000, 1)
out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
print(json.dumps(out))
