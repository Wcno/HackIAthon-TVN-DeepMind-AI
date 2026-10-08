# Experiment: topic classification (G3 step 1)

Date: 2026-10-07 (overnight).
Data: `topic_gold.jsonl`, 300 headlines labeled by Claude Opus (agent), pending human review.
Scripts: `experiments/g3/topic_eval.py`, `experiments/g3/topic_llm.py` (copied to the G3 branch).

## Hypothesis

Embeddings alone (zero-shot or few-shot) can match an LLM per headline on the six topics plus `sin_tema`, and a hybrid can keep LLM quality with fewer calls.

## Setup

- Labels: 7 classes, `sin_tema` 151, economia 42, servicios_publicos 35, eventos_naturales 29, logistica_canal 22, regulacion 14, turismo 7.
- Supervised methods use stratified 5-fold cross-validation on the 300 items, so no item is scored by a model trained on it.
- Gemma prompt: the same topic guidelines used for labeling, strict JSON schema `{tema, confianza}`, one headline per call, temperature 0.
- Hybrid: logistic regression on embeddings; when the gap between its top two class probabilities is below a threshold, the Gemma label is used instead.
- Metric: macro-F1 over 7 classes (and over the 6 editorial topics), plus LLM calls per 300 headlines.

## Results (macro-F1, 7 classes)

| Approach | Macro-F1 7 | Macro-F1 6 | LLM calls / 300 | Works without network |
|---|---|---|---|---|
| Teammate keyword baseline (original: no match -> economía) | 0.361 | 0.421 | 0 | yes |
| Same keywords, no match -> `sin_tema` | 0.451 | 0.410 | 0 | yes |
| Zero-shot similarity to topic descriptions (best: potion) | 0.606 | 0.572 | 0 | yes |
| Nearest centroid, 5-fold CV (best: embeddinggemma-300m) | 0.766 | 0.747 | 0 | yes |
| Logistic regression, 5-fold CV, embeddinggemma-300m | 0.803 | 0.786 | 0 | yes |
| Logistic regression, 5-fold CV, jina-v3 | 0.838 | 0.829 | 0 | yes |
| Gemma per headline | 0.860 | 0.847 | 300 | no (precomputed) |
| **Hybrid: logistic (embeddinggemma-300m) + Gemma when margin < 0.35** | **0.883** | **0.874** | **135** | precomputed |
| Hybrid: logistic (jina-v3) + Gemma when margin < 0.5 | 0.881 | 0.872 | 158 | precomputed |

Gemma per class: economia F1 0.86, logistica_canal 0.93, turismo 0.88, servicios_publicos 0.80 (precision 0.67: it over-assigns public services), eventos_naturales 0.90, regulacion 0.71, sin_tema 0.93.

## Verdict

- Recommended: the hybrid with embeddinggemma-300m (the same model recommended for retrieval), threshold 0.35.
  It beats Gemma alone (+0.02 macro-F1) with 55 % fewer calls; on the full corpus that is about 1,300 Gemma calls instead of 2,941.
- Offline fallback (no LLM at all): logistic regression on embeddinggemma-300m, 0.80.
- The keyword baseline is the G7 baseline: AI adds +0.43 macro-F1 over it.
  The original baseline defaults to `economía` on no match, which is wrong for half the corpus (sports, entertainment); mapping no match to `sin_tema` alone gives +0.09.
- Zero-shot similarity is not good enough (0.61): short Spanish headlines do not sit close to abstract topic descriptions.

## Risks and caveats

- One labeler (an agent) on 300 items; turismo has 7 examples, so its F1 is noisy.
  Human review of the gold set is the first thing to do before quoting these numbers to the jury.
- The hybrid's training set in production is the whole gold set (300); more labels would raise the offline fallback.
- An earlier run of this experiment used a gold file with labels shifted by one row for items 19-99 (a transcription error); it was caught by reading Gemma's confusions, fixed, and every number above uses the corrected file.

## Calls spent

300 Gemma calls (`purpose = g3-tema-llm`), all cached; re-running costs 0.
