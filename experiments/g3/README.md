# G3 experiments (overnight bake-off, 2026-10-07)

Scripts and evaluation data behind `docs/research/local-embeddings-spike.md` (2026-10-07 section) and ADR-0003.
Every label here was made by an agent (Claude Opus, with Gemma for retrieval relevance) and is pending human review.

- `datos/queries.jsonl`, `datos/pools.json`, `datos/judgments.json`: 30 retrieval queries, pooled candidates (row indices of `noticias.csv`), graded relevance.
- `datos/topic_gold.jsonl` (+ `topic_guidelines.md`): 300 headlines with a topic; the same file is `data/labels/temas.jsonl`.
- `datos/pairs_gold.jsonl`: 345 same-event pairs (2 same event, 1 same story, 0 different).
- `datos/*results*`, `datos/timings*.jsonl`, `datos/vps_*.json*`: the measured numbers.

How to rerun (corpus vectors per model are not committed; regenerate them first):

```bash
# GPU venv with onnxruntime-gpu (optional; CPU works, slower):
#   uv venv ~/.cache/whoami/gpu-venv && VIRTUAL_ENV=~/.cache/whoami/gpu-venv uv pip install fastembed-gpu "onnxruntime-gpu[cuda,cudnn]" model2vec scikit-learn
cd experiments/g3 && mkdir -p vectors qvectors dvectors
for m in minilm gemma300m_q4 jina_v3; do ~/.cache/whoami/gpu-venv/bin/python embed_gpu.py $m; done
uv run python retrieval_eval.py score      # needs datos/ copied next to the scripts or paths adjusted
uv run python topic_eval.py gemma300m_q4
taskset -c 0,1 uv run python vps_bench.py gemma300m_q4
```

The scripts were written in a scratch directory and expect their data files in the working directory; copy `datos/*` next to them before running.
Live calls (`topic_llm.py`, `same_event_llm.py`, `retrieval_eval.py judge`, `gemini_embed.py`) go through the shared LLM layer and hit the on-disk cache.
