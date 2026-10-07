"""Quality ceiling: embed a sample with gemini-embedding-2 (cached, ledgered, capped)."""
import json, sys
import numpy as np
sys.path.insert(0, "/home/jwhoami/Development/projects/hackathons/hackiaton-whoamisfc/src")
from whoami.llm import default_llm
from corpus import rows, text

QUERY_PREFIX = "task: search result | query: "
DOC_PREFIX = "title: none | text: "
BUDGET = 860
r = rows()
pool = sorted({int(d) for v in json.load(open("pools.json")).values() for d in v})
sample = list(pool)
chosen = set(sample)
pairs = [json.loads(l) for l in open("pairs_gold.jsonl")]
pairs.sort(key=lambda p: -((p["i"] in chosen) + (p["j"] in chosen)))
for p in pairs:
    need = [x for x in (p["i"], p["j"]) if x not in chosen]
    if len(sample) + len(need) + 30 > BUDGET:
        continue
    sample += need; chosen |= set(need)
queries = [json.loads(l)["consulta"] for l in open("queries.jsonl")]
llm = default_llm()
print("remaining before", llm.remaining("gemini-embedding-2"), "sample", len(sample))
docs = llm.embed("gemini-embedding-2", [DOC_PREFIX + text(r[i]) for i in sample], purpose="g3-step0-techo-embeddings", batch_size=40)
qv = llm.embed("gemini-embedding-2", [QUERY_PREFIX + q for q in queries], purpose="g3-step0-techo-embeddings", batch_size=30)
norm = lambda v: v / np.linalg.norm(v, axis=1, keepdims=True)
full = np.zeros((len(r), docs.shape[1]), dtype=np.float32); full[sample] = norm(docs)
np.save("vectors_gemini/gemini_emb2.npy", full); np.save("qvectors_gemini/gemini_emb2.npy", norm(qv))
json.dump(sample, open("gemini_sample.json", "w"))
print("remaining after", llm.remaining("gemini-embedding-2"))
