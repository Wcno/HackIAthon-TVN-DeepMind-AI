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
