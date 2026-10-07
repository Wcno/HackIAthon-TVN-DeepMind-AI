"""Embed corpus (passages) and eval queries with one model on the NVIDIA GPU; prints timings as JSON."""
import json, os, sys, time
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
import numpy as np
import onnxruntime as ort
ort.preload_dlls()
from corpus import rows, text
from embedders import load

key = sys.argv[1]
queries = [json.loads(l)["consulta"] for l in open("queries.jsonl")]
t0 = time.perf_counter(); embed = load(key, gpu=True); load_s = time.perf_counter() - t0
texts = [text(r) for r in rows()]
embed(texts[:8], False)  # warm-up
t0 = time.perf_counter(); v = embed(texts, False); corpus_s = time.perf_counter() - t0
q = embed(queries, True)
np.save(f"vectors/{key}.npy", v); np.save(f"qvectors/{key}.npy", q)
print(json.dumps({"model": key, "device": "gpu", "providers": getattr(embed, "providers", ["model2vec-numpy"]), "load_s": round(load_s, 2), "corpus_embed_s": round(corpus_s, 2), "dim": int(v.shape[1])}))
