# G4 experiments (overnight, 2026-10-07)

Scripts and dev sets behind `docs/research/g3-g4-research/g4-generation.md`.
The dev sets are agent-labeled (Claude Opus) and are NOT the reserved G7 benchmark.

## Data

- `devset_consultas.jsonl`: 40 queries, 10 per type (answerable, contradiction or ambiguity, no answer, adversarial), with the expected state and key facts.
- `devset_sinteticas.jsonl`: 8 synthetic news items (`.invalid` URLs) for synthetic contradictions and injected instructions.
- `pares_mismo_evento.jsonl`: the same-event pairs of the G3 bake-off, used for negative contradiction pairs.
- `resultados/`: one JSONL per run (model, configuration), the raw material of the report.

## How to rerun

From the repository root; the evidence is `data/processed/evidencias.jsonl` (override with `WHOAMI_DEV_EVIDENCE`).

```bash
uv run --all-groups python experiments/g4/query_devset.py retrieval                          # BM25 vs embeddings vs hybrid recall@8
uv run --all-groups python experiments/g4/query_devset.py answer --model gemini-3.5-flash-lite   # query box on the 40 dev queries
uv run --all-groups python experiments/g4/case_files_devset.py --model gemini-3.5-flash-lite --data data/processed --groups 5 --entailment
uv run --all-groups python experiments/g4/verifier_perturbations.py --model gemini-3.5-flash-lite
uv run --all-groups python experiments/g4/contradictions_eval.py --model gemma-4-26b-a4b-it
uv run --all-groups python experiments/g4/injection.py --model gemma-4-26b-a4b-it
```

Live calls go through the shared LLM layer (`whoami.llm`): cached on disk on the machine that made them, ledgered, capped.

Discarded configurations (single-threshold grouping, LLM and combined gates, single-shot generation) were measured at commit `07139a3`; check out that commit to rerun them.
