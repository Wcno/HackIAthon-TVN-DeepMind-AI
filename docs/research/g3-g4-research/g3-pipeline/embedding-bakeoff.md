# Step 0: local embedding bake-off (follow-up to `docs/research/local-embeddings-spike.md`)

Date: 2026-10-07 (overnight).
Corpus: 2,941 items of `data/processed/noticias.csv`, text = `titulo + ". " + descripcion` (description only when present).
Batch embedding on an NVIDIA RTX 4050 Laptop GPU (6 GB, `onnxruntime-gpu` 1.30, CUDA execution provider checked per run).
Query-time numbers on CPU pinned to 2 cores with `taskset -c 0,1` and 2 ONNX threads, to approximate a small VPS.

## Evaluation data (agent-labeled, pending human review)

- Retrieval: 30 Spanish editor-style queries; pooled top-10 of every model plus BM25 plus `gemini-embedding-2` (932 query-document pairs), graded 0/1/2 by Gemma; 1 pair left ungraded.
  Spot check of 25 judgments by Claude Opus: 24/25 agree on the "directly relevant" (grade 2) boundary, 19/25 on the exact grade (Gemma is lenient with grade 1).
  recall@5 uses grade 2 only, so it is the more trustworthy number.
- Topics: 300 headlines (`topic_gold.jsonl`), 7 classes, labeled by Claude Opus.
- Same event: 345 pairs labeled 2 (same event, 100), 1 (same running story, 89), 0 (different, 156); weather forecasts labeled by rule (same day = same event).

## Results

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

## Findings

- embeddinggemma-300m is the best retrieval model and the q4 build keeps almost all of it (nDCG@10 -0.012, inside the noise of 30 queries) at 65 % of the RAM.
  q4 vectors have mean cosine 0.97 with fp32 vectors: the corpus and the queries must use the same build.
- The q8 build is slower and heavier than fp32 on this CPU (130 ms, 1.5 GB): its quantized operators fall back to slow kernels. Discard.
- jina-v3 has the best topic and grouping numbers by a hair, but 405 ms per query and 6.6 GB RSS on CPU make it unusable on a VPS.
- potion (static model): `model2vec` with numpy does NOT fix the RAM problem; it peaks at 1.6 GB, worse than its ONNX build (1.16 GB). The 1.2 GB comes from the 500K-token vocabulary matrix, not from onnxruntime. Negative result.
- MiniLM (the `prod` plan) is the weakest retriever (nDCG 0.77), at the level of BM25.
- No model fits a strict 512 MB server; embeddinggemma q4 (587 MB) is the closest and fits 1 GB with room for the app.
- The three models that failed to load from the Hugging Face cache (embeddinggemma, e5-large, jina-v3) load after copying the snapshot with symlinks resolved (`cp -rL`) into `~/.cache/whoami/models/local/<model>/`.
- Production does not need `fastembed`: `onnxruntime` + `tokenizers` with the `sentence_embedding` output reproduce fastembed's vectors (cosine 0.9998).

## Recommendation

`google/embeddinggemma-300m`, ONNX q4 build (`onnx-community/embeddinggemma-300m-ONNX`, revision `5090578d9565bb06545b4552f76e6bc2c93e4a66`), with prefixes `title: none | text: ` (documents) and `task: search result | query: ` (queries).
Corpus vectors committed as float16 with a manifest; only queries are embedded at runtime (30 ms, 587 MB).
Open decision for the team: if the server has 2 GB, fp32 gains about 0.01 nDCG; not worth the RAM on 1 GB.
