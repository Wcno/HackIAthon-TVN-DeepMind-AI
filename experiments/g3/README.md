# G3 experiments (overnight bake-off, 2026-10-07)

Scripts and evaluation data behind `docs/research/g3-g4-research/g3-pipeline/` and ADR-0003.
Every label here was made by an agent (Claude Opus, with Gemma for retrieval relevance) and is pending human review.

## Data (`datos/`)

- `queries.jsonl`, `pools.json`, `judgments.json`: 30 retrieval queries, pooled candidates (row indices of `data/processed/noticias.csv`), graded relevance.
- `bm25_rank.json`, `bm25_rank_full.json`: BM25 rankings of the 30 queries (`bm25.py`), the keyword baseline.
- `topic_gold.jsonl` (+ `topic_guidelines.md`): 300 headlines with a topic; the same labels are `data/labels/temas.jsonl`.
- `pairs_gold.jsonl`: 345 same-event pairs (2 same event, 1 same story, 0 different).
- `*results*`, `timings*.jsonl`, `vps_*.json*`, `topic_pred_gemma.jsonl`, `same_event_gemma.json`, `gemini_sample.json`: the measured numbers and model outputs.

## How to rerun

Run from the repository root. Model vectors are not committed: generate them first (they go to `experiments/g3/vectors/`, `qvectors/`, `dvectors/`, all gitignored).

```bash
# Batch embedding on an NVIDIA GPU needs a separate venv (CPU also works with the project venv, slower):
#   uv venv ~/.cache/whoami/gpu-venv
#   VIRTUAL_ENV=~/.cache/whoami/gpu-venv uv pip install fastembed-gpu "onnxruntime-gpu[cuda,cudnn]" model2vec scikit-learn
for m in minilm gemma300m gemma300m_q4 jina_v3; do ~/.cache/whoami/gpu-venv/bin/python experiments/g3/embed_gpu.py $m; done
~/.cache/whoami/gpu-venv/bin/python experiments/g3/embed_descriptions.py gemma300m_q4

uv run --all-groups python experiments/g3/retrieval_eval.py score          # recall@5, nDCG@10 per model
uv run --all-groups python experiments/g3/topic_eval.py gemma300m_q4       # topic macro-F1 per approach
uv run --all-groups python experiments/g3/grouping_eval.py                 # pairwise F1 per grouping method
uv run --all-groups python experiments/g3/context_eval.py                  # official context: rules vs embeddings
taskset -c 0,1 uv run --all-groups python experiments/g3/vps_bench.py gemma300m_q4   # CPU latency and RSS, 2 cores
```

Live calls (`topic_llm.py`, `same_event_llm.py`, `retrieval_eval.py judge`, `gemini_embed.py`) go through the shared LLM layer (`whoami.llm`): cached on disk on the machine that made them, ledgered, capped.
`peaks.py` prints the peak calls and tokens per calendar minute from the ledger.

Local models are expected under `~/.cache/whoami/models/` (Hugging Face cache layout); embeddinggemma, multilingual-e5-large and jina-v3 must be copied with symlinks resolved into `~/.cache/whoami/models/local/<model>/` to load (see `docs/research/local-embeddings-spike.md`).
