# Experiment: duplicate grouping (T02, CU-03)

Date: 2026-10-07 (overnight).
Data: `pairs_gold.jsonl`, 345 candidate pairs inside a 7-day window, labeled by Claude Opus (agent), pending human review.
Labels: 2 same event (100), 1 same running story but a different development (89), 0 different (156).
Weather forecasts were labeled by rule: same day = same event.
Candidates were sampled by similarity bands from three models plus token overlap, so the set is not biased toward one model.

## Hypothesis

Average-linkage clustering inside a time window beats a single cosine threshold, because a threshold chains a running story into one blob; an LLM verdict on borderline pairs fixes what the embedding cannot tell.

## Metric

Pairwise precision, recall and F1 of "same event" on labeled pairs, excluding the ambiguous label 1 (245 pairs).
"Loose" numbers count label 1 as positive.

## Results (best setting per method)

| Method | Model | P | R | F1 strict | F1 loose | Groups > 1 | Largest |
|---|---|---|---|---|---|---|---|
| Single link, cosine >= 0.75, 72 h window (current `prod`-style) | jina-v2-es | 0.65 | 0.79 | 0.71 | 0.62 | 466 | 18 |
| Single link + entity/number overlap bonus | jina-v3 | 0.58 | 0.80 | 0.68 | 0.61 | 477 | 18 |
| HDBSCAN, min cluster 2, window | MiniLM | 0.73 | 0.79 | 0.76 | 0.66 | 781 | 14 |
| **Agglomerative, average linkage, distance < 0.25-0.30, window** | embeddinggemma-300m | 0.82 | 0.79 | **0.81** | 0.65 | 560 | 8 |
| Same, q4 build (the chosen model) | embeddinggemma-300m q4 | | | 0.81-0.82 | | | |

- Held-out check of the threshold (tune on half the pairs, score the other half, 20 random splits): F1 0.797 ± 0.024, so the threshold is not overfit.
- Entity/number overlap adds nothing: shared capitalized words and numbers are already in the embedding.
- Single link chains a running story (the Messi farewell, the electoral reform) into groups of 18-31 items; average linkage caps groups at 8-9.
- "Same story" pairs (label 1) are mostly split: loose F1 is 0.65. That is the intended behaviour: a new development is a new event with its own score, and novelty (N) is computed against earlier groups.

## LLM on the grey zone

- Grey zone: pairs inside 72 h with cosine 0.65-0.80 (embeddinggemma); 1,460 such pairs in the corpus with fp32 vectors, 1,552 with q4.
- On the 63 labeled pairs in that band, Gemma ("same concrete event?", strict JSON boolean) is right on 61/63; agglomerative clustering on 48/63.
- The pipeline uses the verdicts as distance overrides (same event -> 0, different -> 1) before average linkage.
- End-to-end score of the hybrid: see the pipeline run section of the README (filled after the run).

## Provenance

- No agency marker (EFE, AFP, Reuters...) appears in the corpus except one AFP mention.
- The corpus is TVN plus six official sources, so "independent provenance" mostly separates an official press release from TVN's coverage.
- Near-identical text from different outlets takes the earliest item's provenance (token Jaccard >= 0.8), so a press release copied by an outlet counts once.

## Calls spent

63 Gemma calls on labeled grey pairs, 554 on the fp32 corpus grey zone (stopped when q4 was chosen; cached), plus the pipeline run.
