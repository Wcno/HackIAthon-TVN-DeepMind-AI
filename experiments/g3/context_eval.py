"""Step 5: explicit keyword rules vs embedding similarity for linking news to an official indicator family.

    uv run --all-groups python experiments/g3/context_eval.py

Needs the local embedding model and the corpus vectors (`whoami embed`); writes `datos/context_links.json`.
"""
import json
from pathlib import Path
import numpy as np
from whoami.embeddings import Embedder
from whoami.pipeline.context import link_context
from whoami.pipeline.evidence import load_news_rows, load_official_evidence
from whoami.pipeline.run import load_vectors, default_vectors_path
from whoami.schemas import parse_utc
from whoami.embeddings import document_text

DATA = Path(__file__).parent / "datos"

FAMILIES = {
    "inflacion": "inflación y precios al consumidor en Panamá",
    "desempleo": "desempleo y tasa de desempleo en Panamá",
    "pib": "crecimiento económico y producto interno bruto de Panamá",
    "exportaciones": "exportaciones de bienes y servicios de Panamá",
    "sismo": "sismo o terremoto en Panamá",
}
rows = load_news_rows(); v = load_vectors(default_vectors_path(), rows).astype(np.float32)
v /= np.linalg.norm(v, axis=1, keepdims=True)
official = load_official_evidence()
q = Embedder().embed_queries(list(FAMILIES.values()))
sims = v @ q.T
fam = list(FAMILIES)
rule_links, emb_links = {}, {}
for i, r in enumerate(rows):
    links, _ = link_context(document_text(r), parse_utc(r["fecha_publicacion"]), "economia", official)
    if links:
        rule_links[i] = links[0].id_evidencia
for thr in (0.55, 0.6, 0.65, 0.7):
    n = int((sims.max(1) >= thr).sum()); print("emb threshold", thr, "links", n)
THR = 0.5
for i in np.nonzero(sims.max(1) >= THR)[0]:
    emb_links[int(i)] = fam[int(sims[i].argmax())]
print("rule links", len(rule_links), "emb links", len(emb_links), "both", len(set(rule_links) & set(emb_links)))
out = []
for i in sorted(set(rule_links) | set(emb_links)):
    out.append({"i": i, "titulo": rows[i]["titulo"][:110], "regla": rule_links.get(i), "emb": emb_links.get(i), "sim": round(float(sims[i].max()), 3)})
json.dump(out, (DATA / "context_links.json").open("w"), ensure_ascii=False, indent=0)
for o in out: print(o["i"], "| R:", (o["regla"] or "-")[:28], "| E:", o["emb"] or "-", o["sim"], "|", o["titulo"])
