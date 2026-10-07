# G3 · AI pipeline (issue #21): overnight report

Status: done for the night (2026-10-07, about 13:30 UTC).
Branch: `feat/g3-g4-ia` (developed on `proto/g3-pipeline`).

## Done

- Shared LLM layer on `proto/base` (OpenAI-compatible client, disk cache, ledger, hard cap per model, rate limiter with 20-30 % headroom that resumes from the ledger across processes, retries on 429/500/503/timeouts, invalid JSON never cached).
- Step 0 embedding bake-off: 10 local models + `gemini-embedding-2` ceiling → [embedding-bakeoff.md](embedding-bakeoff.md), draft ADR-0003 on the branch (`docs/adr/0003-local-embeddings-embeddinggemma.md`), research doc extended (`docs/research/local-embeddings-spike.md`).
- Corpus vectors committed: `data/processed/embeddings/embeddinggemma-300m-q4.npy` (float16, 4.5 MB) + `manifest.json` (model, revision, file SHA-256, prefixes, text recipe, vectors SHA-256, ids).
- Topic classification bake-off → [topic-classification.md](topic-classification.md).
- Duplicate grouping bake-off → [grouping.md](grouping.md).
- Pipeline code (`src/whoami/pipeline/`, `src/whoami/embeddings.py`): evidence for every source, provenance (agency markers, near-identical copies), recirculation (metadata rule and in-group rule), official context by explicit rules (with a fixed quake false positive), score R/I/U/N/E with written rules and Spanish justifications, evidence state, hybrid topics, agglomerative grouping with Gemma verdicts on the grey zone, `whoami embed`, `whoami pipeline [--sin-llm]`.
- Experiment scripts and labeled data: `experiments/g3/` (see its README).

## Setup facts found tonight

- Gemma (`gemma-4-26b-a4b-it`) via the OpenAI-compatible endpoint: with `response_format` json_schema it answers in about 1 s; without a schema it emits a `<thought>` block and took 33 s.
  It sometimes degenerates into endless whitespace inside JSON (one call hung 600 s): every call now has `max_tokens`, a 90 s timeout, and invalid JSON is not cached.
- Gemma also occasionally appends a stray "```" after valid JSON; the parser reads the first JSON value.
- The embedding endpoint limits texts per minute (about 100), not requests; the limiter now counts texts.
- Corpus: 2,941 items (2,820 TVN, 121 from 6 official sources); 2,771 are headline-only. About half is sports, entertainment, crime and world politics: `sin_tema` is the largest class.
- No agency marker appears in the corpus except one AFP mention: provenance counting mostly separates official sources from TVN.
- T03 on real data: G1 excludes items by their ORIGINAL publication date, so recirculated old articles never reach `noticias.csv` (largest gap between modification and publication in the corpus: 1 day).
  Open decision for G1: keep items whose `lastmod` falls in the window even when the original date is older, so T03 can be shown on real data. The demo set (`G-006`) shows it meanwhile.
- GPU: an NVIDIA RTX 4050 Laptop (6 GB) did the batch embedding through a separate venv (`~/.cache/whoami/gpu-venv`, `onnxruntime-gpu`); query-time numbers are CPU on 2 cores, like a small VPS.

## Experiments (verdicts)

| Task | Recommended | Evidence | Discarded |
|---|---|---|---|
| Embeddings | embeddinggemma-300m ONNX q4 | nDCG@10 0.859 (fp32 0.871, Gemini ceiling 0.887), 587 MB, 30 ms/query on 2 cores | MiniLM (0.77, BM25 level), jina-v3 (6.6 GB, 405 ms), potion (1.2-1.6 GB RAM), q8 build (slower than fp32) |
| Topics | Logistic regression on embeddings + Gemma when margin < 0.35 | macro-F1 0.883 with 45 % of the calls; Gemma alone 0.860; embeddings alone 0.81 (offline fallback) | Keyword baseline (0.36; G7 baseline), zero-shot similarity (0.61), nearest centroid (0.78) |
| Grouping | Agglomerative average linkage, distance < 0.275, 72 h window, Gemma verdicts on cosine 0.65-0.80 | Pairwise F1 0.81-0.82 embeddings only (held-out 0.80 ± 0.02); Gemma 61/63 vs clustering 48/63 on grey pairs | Single link threshold (0.71, chains stories), HDBSCAN (0.76), entity/number overlap (no gain) |
| Score | Rules as written in `scoring.py` (weights 30/25/20/15/10 kept from §4) | Every component has a Spanish justification; N ignores group size | — |
| Official context | Explicit keyword rules per indicator; quakes only by date + location | Never forced; a "terremoto en Colombia" false positive was found and fixed | Embedding-similarity linking: not run (see open decisions) |

## Open decisions for the team

- Embedding build: q4 (recommended for a 1 GB server) or fp32 (+0.012 nDCG@10 on 2 GB).
- Grey-zone band and agglomerative threshold (0.65-0.80 and 0.275 were set on this corpus).
- Topic margin 0.35 vs 0.2 (0.870 macro-F1 with 28 % of the calls instead of 45 %).
- Score weights: kept at the §4 suggestion; no editor ranking exists yet to tune them (Precision@5 needs an editor's independent pick).
- G1: keep recirculated items (see T03 above).
- Human review of the three labeled sets (`data/labels/temas.jsonl`, `experiments/g3/datos/pairs_gold.jsonl`, the relevance judgments).

## Skipped (with reason)

- Embedding-similarity linker for official context (step 5, second approach): the official package has 6 World Bank indicators, 6 INEC series and USGS quakes; a keyword rule per indicator is explainable and cannot invent a link, while similarity on 12 short labels mostly links by topic, not by measurement. Not measured; listed as an open question.

## How to run

```bash
uv run whoami embed                  # corpus vectors (2 min on CPU), already committed
uv run whoami pipeline --sin-llm     # offline: logistic topics, embedding-only grouping
WHOAMI_BUDGET_SINCE=2026-10-07T06:30:00Z uv run whoami pipeline   # with Gemma (cached calls are free)
uv run python -m whoami.llm.ledger --since 2026-10-07T06:30:00Z    # calls per model
```

## Real pipeline run (committed: `data/processed/grupos.jsonl`, `evidencias.jsonl`)

`whoami pipeline` with Gemma: 2,142 groups (634 with several items, largest 10), ranges alto 81 / medio 802 / bajo 1,259, 3,713 evidence records, 16 groups with official context.
Topics: sin_tema 1,317, servicios_publicos 311, economia 215, eventos_naturales 121, regulacion 101, logistica_canal 50, turismo 27.
LLM calls: 1,081 topic calls (the hybrid sent 37 % of the corpus to Gemma) and 1,552 same-event verdicts; a re-run is fully cached (2 s, 0 network calls).

Grouping end to end on the labeled pairs (strict, label 1 excluded):

| Grouping | P | R | F1 |
|---|---|---|---|
| Agglomerative, embeddings only (`--sin-llm`) | 0.823 | 0.790 | 0.806 |
| Agglomerative + Gemma verdicts on the grey zone (default) | 0.862 | 0.810 | 0.835 |

### Ranking: the main risk

The top of the real inbox is fresh budget sessions and official press releases ("Mides solicita $47 millones", a training workshop on a food regulation, Vietnamese shipping companies meeting the President); the month's big stories (Canal transits, the blackout, influenza deaths, the electoral reform, the copper mine) rank lower.
Cause: urgency is the age at the cutoff over a 30-day corpus, and any money figure adds +0.2 impact, while R is 1.0 for almost every Panamanian story with a topic.
This needs an editor's independent top-5 (Precision@5) before tuning; candidate fixes: an impact component rated by the LLM with a written justification, coverage breadth as an impact signal (distinct from novelty), and a weaker money bonus.

## Calls per model (whole night)

See [../g4-generation.md](../g4-generation.md#calls-per-model-whole-night-both-issues-from-the-ledger): Gemma 3,484 network calls (cap 5,000), gemini-3.1-flash-lite 98 (cap 200), gemini-3.5-flash-lite 81 (cap 100), gemini-embedding-2 795 texts embedded (cap 900).
G3 alone: about 2,900 Gemma calls (topics 1,081 + same-event 1,552 + bake-off judging and labeling).
