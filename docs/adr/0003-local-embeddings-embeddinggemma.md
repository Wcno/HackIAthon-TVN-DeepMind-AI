---
status: proposed
date: 2026-10-07
supersedes: the embedding part of 0001-gemini-free-tier-for-embeddings-and-generation.md
---

# Local embeddings with embeddinggemma-300m (ONNX q4)

Headline embeddings are computed locally with `google/embeddinggemma-300m`, ONNX q4 build, through `onnxruntime` and `tokenizers` (no PyTorch, no `fastembed` at runtime).
The corpus vectors are computed once, stored as float16 next to a manifest, and committed; only the query is embedded at runtime.
Gemini stays for generation only.

## Why

- The Gemini free tier counts embeddings per text: about 100 texts per minute and 1,000 per day, so the 2,941-item corpus alone needs three days of quota (measured, issue #21).
- On 30 labeled queries embeddinggemma reaches the quality of `gemini-embedding-2` (nDCG@10 0.871 against 0.887, recall@5 0.885 against 0.868), and it is the best of ten local models (`docs/research/local-embeddings-spike.md`, 2026-10-07 section).
- The q4 build keeps that quality (nDCG@10 0.859, recall@5 0.874) at 587 MB peak RSS and 30 ms per query on 2 CPU cores, against 900 MB for fp32.
- Local vectors work offline, which T10 (D-01) requires.

## Considered options

- **`gemini-embedding-2`** (ADR-0001): quality ceiling, but the daily text quota does not cover the corpus.
- **MiniLM-L12** (the `prod` plan): smallest (665 MB, 4 ms), but the weakest retriever (nDCG@10 0.77, the level of BM25).
- **potion-multilingual-128M**: fastest, but 1.2-1.6 GB RSS (its vocabulary matrix) and weaker retrieval (0.80).
- **jina-embeddings-v3**: best topic and grouping scores by a small margin, but 405 ms per query and 6.6 GB RSS on CPU.
- **embeddinggemma fp32**: +0.012 nDCG@10 over q4 for +313 MB; worth it only on a 2 GB server.
- **embeddinggemma q8**: slower and heavier than fp32 on this CPU; discarded.

## Consequences

- The model is pinned (repo, revision `5090578d9565bb06545b4552f76e6bc2c93e4a66`, file SHA-256 in the manifest). Changing model or build means recomputing every vector: q4 and fp32 vectors differ (mean cosine 0.97).
- Prefixes are part of the contract: documents `title: none | text: `, queries `task: search result | query: `.
- No strict 512 MB tier fits; the API needs about 1 GB. The pipeline that builds the vectors runs offline (235 s on 2 CPU cores, 9 s on a GPU).
- The model files (218 MB) are downloaded once with `whoami` (pinned) into `~/.cache/whoami/models/local/embeddinggemma-300m-q4`, never into `/tmp`.
- Gemma's license (Gemma Terms of Use) applies to the embedding model; it allows this use, but it must be listed with the other conditions of the project.

## Follow-up, 2026-10-08

The historical quality figures above used model-generated relevance judgments, still pending human review. The old function called `recall@5` divided by `min(relevant, 5)`; it is not conventional recall. The historical 235-second full rebuild belongs to fp32, not a verified q4 rebuild on this PC. These observations do not establish a human-validated winner or a working free cloud deployment. q4 stays in use while the approved [blind development comparison](../embedding-validation.md) measures separate model spaces, genuine human judgments, coverage and current CPU performance. Generation stays with Gemini. The no-card route presently prepared for the full application is a temporary private PC tunnel; independent cloud compatibility remains unverified.
