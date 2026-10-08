# Local embeddings spike (fastembed + ONNX)

Date: 2026-10-06.
Branch: `mvp-jwhoami`.
Corpus: 2,821 TVN news items (`data/processed/noticias.csv`), text = `titulo + ". " + descripcion`.
Machine: 22 CPUs, 31 GB RAM, `fastembed` 0.8.1, CPU only.

## TL;DR

- Recommendation: use `paraphrase-multilingual-MiniLM-L12-v2` locally.
  It is the smallest option, matches the `prod` plan, and was on-topic for 4 of 5 queries (the Canal query failed, see below).
- It does NOT fit a 512 MB server as measured: a query-only process peaked at about 660-680 MB.
  It fits a 1 GB tier comfortably.
- If the deploy tier is strictly 512 MB, local ONNX is not viable for queries with these models.
  Keep Gemini for corpus and query embeddings (1 text per query is far below the 1,000 texts/day limit).
- Local embedding removes the Gemini quota entirely for the corpus: MiniLM embeds all 2,821 items in 8.8 s on 22 cores.
- `potion-multilingual-128M` had the best top-5 results on our queries and the fastest embedding, but needs about 1.2 GB RSS.
  It is worth a follow-up if the server has 2 GB.
- `paraphrase-multilingual-mpnet-base-v2` is not worth it: about 2 GB RSS, 3x slower, no clear quality gain here.

## Measurements

All numbers measured in this spike, each model in its own process.
RSS is `resource.getrusage` `ru_maxrss` (peak).

| Metric | MiniLM-L12-v2 | mpnet-base-v2 | potion-multilingual-128M |
|---|---|---|---|
| Dimensions | 384 | 768 | 256 |
| ONNX file on disk | 225 MB (quantized build) | about 1.1 GB | 489 MB |
| Corpus: model load (warm cache) | 0.7 s | not rerun, 1.1 s in query run | not rerun, 1.2 s in query run |
| Corpus: embed 2,821 texts, batch 64 | 8.8 s | 26.3 s | 0.09 s |
| Corpus: peak RSS | 938 MB | 1,990 MB | 1,485 MB |
| Query-only: model load (warm cache) | 0.64 s | 1.07 s | 1.16 s |
| Query-only: first query latency | 9 ms | 11 ms | 1 ms |
| Query-only: second query latency | 4 ms | 9 ms | under 1 ms |
| Query-only: peak RSS | 663 MB | 1,889 MB | 1,159 MB |
| First download (this network) | not measured (cached) | 119 s | 60 s |

Notes:

- Limiting ONNX threads to 1 or 2 (`threads=`) did not reduce query RSS for MiniLM (662 MB both).
  Memory is dominated by the model and runtime, not by thread buffers.
- Python plus numpy plus onnxruntime baseline is part of these numbers, so they are what a real server process would show.
- Cache: `fastembed` stores models under `/tmp/fastembed_cache` by default (observed on this machine).
  Set `cache_dir=` or the `FASTEMBED_CACHE_PATH` env var for a persistent location, see https://github.com/qdrant/fastembed.
- Cache layout is Hugging Face hub style (`models--<org>--<name>/snapshots/...`).
- The supported-model sizes quoted in the task (0.22 GB, 1.0 GB, 0.51 GB) match the files observed.

## Quality results

Single judge (the spike author), 5 results per query, relevant = clearly on the query topic.

| Query | MiniLM | mpnet | potion |
|---|---|---|---|
| Canal de Panamá tránsitos y sequía | 0/5 | 0/5 | 5/5 |
| inflación y precios de alimentos | 5/5 | 5/5 | 5/5 |
| inundaciones y lluvias en provincias | 5/5 | 4/5 | 5/5 |
| turismo y llegada de visitantes | 5/5 | 5/5 | 5/5 |
| protestas y cierres de calles | 4/5 | 4/5 | 5/5 |
| Total | 19/25 | 18/25 | 25/25 |

Observations:

- The paraphrase models (MiniLM, mpnet) pulled generic "Clima en Panamá" weather items for the Canal query and missed the real transit articles.
  potion returned "Canal de Panamá aumentará a 33 los tránsitos diarios" and similar, which is what the query meant.
- mpnet drifted to foreign events for "protestas" and "inundaciones" (Tailandia, Madrid, Chile).
- The 5-query sample is small, so treat the potion win as a signal, not proof.
- Duplicate headlines exist in the corpus (same title appears twice with similarity 1.0), so top-5 lists can repeat an item.
  Deduplicate by title before indexing.

### Same-event pairs vs random baseline

Three distinct headlines about the same event (cosine similarity of full `titulo + descripcion` text):

| Pair | MiniLM | mpnet | potion |
|---|---|---|---|
| Airbnb vs hoteleros, alquileres de corta estancia (rows 334, 364) | 0.907 | 0.911 | 0.846 |
| EEUU dona 4 drones a Panamá (rows 1895, 1898) | 0.886 | 0.915 | 0.853 |
| Calle 71 San Francisco cambia a un solo sentido (rows 2556, 2664) | 0.890 | 0.949 | 0.909 |
| Random pairs, mean (1,000 pairs) | 0.090 | 0.141 | 0.084 |
| Random pairs, p95 (1,000 pairs) | 0.307 | 0.358 | 0.251 |

All three models separate same-event pairs (0.85-0.95) from random pairs (p95 at most 0.36) by a wide margin.
Pairs were picked from MiniLM's high-similarity candidates, so MiniLM is slightly favored by selection.

## Risks

- Memory: no tested model fits 512 MB.
  MiniLM peaked at 663-682 MB after loading and answering one query.
  A host that counts virtual memory or has a cold-start spike could be killed even on 1 GB, so test on the real tier.
- Memory not tried: other ONNX runtime options (arena off, memory-mapped loading), smaller quantizations.
  They might lower RSS but were not measured.
- Re-embedding is required if the model changes, and local vectors cannot be mixed with Gemini vectors (different spaces and dimensions).
- Query-time model load is 0.6-1.2 s warm, so load once at startup, never per request.
- First run downloads the model (60-120 s here for the larger ones), so bake it into the deploy image or point the cache at a persistent path.
- Default cache in `/tmp` can be wiped between deploys.
- Quality was judged on 5 queries by one person.
  Before committing, build a small labelled query set (20 or more) and compare recall@5 for MiniLM and potion.
- ADR `docs/adr/0001-gemini-free-tier-for-embeddings-and-generation.md` rejected local models because of PyTorch size.
  This spike shows ONNX avoids PyTorch but memory is still above 512 MB, so the ADR's constraint is only partly lifted.
- The MiniLM build used by `fastembed` is a quantized ONNX export (`qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`), which may differ slightly from the PyTorch model in `docs/PLAN.md`.

## Sources

- fastembed: https://github.com/qdrant/fastembed
- MiniLM model: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- mpnet model: https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2
- potion model: https://huggingface.co/minishlab/potion-multilingual-128M
- Quantized MiniLM ONNX used by fastembed: https://huggingface.co/qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q

## Follow-up: ten-model bake-off (2026-10-07)

This section extends the spike with a labeled evaluation set; the original measurements above are unchanged.
Scripts and data: `experiments/g3/`. Decision: ADR-0003.

### Evaluation data (agent-labeled, pending human review)

- Retrieval: 30 Spanish editor-style queries; pooled top-10 of every model plus BM25 plus `gemini-embedding-2` (932 query-document pairs), graded 0/1/2 by Gemma; 1 pair left ungraded.
  Spot check of 25 judgments by Claude Opus: 24/25 agree on the "directly relevant" (grade 2) boundary, 19/25 on the exact grade (Gemma is lenient with grade 1).
  recall@5 uses grade 2 only, so it is the more trustworthy number.
- Topics: 300 headlines (`topic_gold.jsonl`), 7 classes, labeled by Claude Opus.
- Same event: 345 pairs labeled 2 (same event, 100), 1 (same running story, 89), 0 (different, 156); weather forecasts labeled by rule (same day = same event).

### Results

| Model | Dim | recall@5 | nDCG@10 | Topic F1 (logistic, CV) | Grouping F1 (agglomerative) | GPU corpus s | CPU-2 query ms | Query RSS MB |
|---|---|---|---|---|---|---|---|---|
| **embeddinggemma-300m q4** | 768 | 0.874 | 0.859 | 0.812 | 0.818 | 9.5 | 30 | **587** |
| embeddinggemma-300m fp32 | 768 | 0.885 | 0.871 | 0.803 | 0.810 | 9.0 | 24 | 900 |
| embeddinggemma-300m q8 | 768 | 0.885 | 0.875 | 0.799 | 0.804 | 9.9 | 130 | 1,509 |
| jina-embeddings-v3 | 1024 | 0.846 | 0.845 | 0.838 | 0.821 | 33.0 | 405 | 6,601 |
| jina-embeddings-v2-base-es | 768 | 0.839 | 0.834 | 0.798 | 0.818 | 8.3 | 18 | 936 |
| multilingual-e5-large | 1024 | 0.829 | 0.825 | 0.745 | 0.759 | 21.1 | 54 | 1,558 |
| Qwen3-Embedding-0.6B (quantized) | 1024 | 0.813 | 0.815 | 0.811 | 0.804 | 45.2 | 378 | 1,771 |
| potion-multilingual-128M (ONNX / model2vec) | 256 | 0.763 | 0.804 | 0.752 | 0.758 | 0.1 | 0.1 | 1,161 / 1,601 |
| multilingual-e5-small | 384 | 0.761 | 0.792 | 0.743 | 0.795 | 2.6 | 5 | 916 |
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 0.728 | 0.770 | 0.786 | 0.804 | 1.3 | 4 | 665 |
| paraphrase-multilingual-mpnet-base-v2 | 768 | 0.734 | 0.758 | 0.794 | 0.831 | 6.4 | 11 (22 cores) | 1,891 |
| BM25 (keywords, baseline) | n/a | 0.759 | 0.764 | n/a | n/a | n/a | n/a | n/a |

Quality ceiling, `gemini-embedding-2` (768 dims), on the 830-document sample it embedded (all models ranked inside the same sample): recall@5 0.868, nDCG@10 0.887.
On that sample embeddinggemma-300m fp32 scores recall@5 0.885, nDCG@10 0.871: local quality is at the cloud ceiling.

Rebuilding the corpus vectors on 2 CPU cores with embeddinggemma fp32 took 235 s (peak RSS 1.67 GB); with the GPU, 9 s.

### Findings

- embeddinggemma-300m is the best retrieval model and the q4 build keeps almost all of it (nDCG@10 -0.012, inside the noise of 30 queries) at 65 % of the RAM.
  q4 vectors have mean cosine 0.97 with fp32 vectors: the corpus and the queries must use the same build.
- The q8 build is slower and heavier than fp32 on this CPU (130 ms, 1.5 GB): its quantized operators fall back to slow kernels. Discard.
- jina-v3 has the best topic and grouping numbers by a hair, but 405 ms per query and 6.6 GB RSS on CPU make it unusable on a VPS.
- potion (static model): `model2vec` with numpy does NOT fix the RAM problem; it peaks at 1.6 GB, worse than its ONNX build (1.16 GB). The 1.2 GB comes from the 500K-token vocabulary matrix, not from onnxruntime. Negative result.
- MiniLM (the `prod` plan) is the weakest retriever (nDCG 0.77), at the level of BM25.
- No model fits a strict 512 MB server; embeddinggemma q4 (587 MB) is the closest and fits 1 GB with room for the app.
- The three models that failed to load from the Hugging Face cache (embeddinggemma, e5-large, jina-v3) load after copying the snapshot with symlinks resolved (`cp -rL`) into `~/.cache/whoami/models/local/<model>/`.
- Production does not need `fastembed`: `onnxruntime` + `tokenizers` with the `sentence_embedding` output reproduce fastembed's vectors (cosine 0.9998).

### Recommendation

`google/embeddinggemma-300m`, ONNX q4 build (`onnx-community/embeddinggemma-300m-ONNX`, revision `5090578d9565bb06545b4552f76e6bc2c93e4a66`), with prefixes `title: none | text: ` (documents) and `task: search result | query: ` (queries).
Corpus vectors committed as float16 with a manifest; only queries are embedded at runtime (30 ms, 587 MB).
Open decision for the team: if the server has 2 GB, fp32 gains about 0.01 nDCG; not worth the RAM on 1 GB.
