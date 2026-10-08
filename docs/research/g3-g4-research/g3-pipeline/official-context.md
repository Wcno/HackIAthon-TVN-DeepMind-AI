# Experiment: official context link (T04, step 5)

Date: 2026-10-07 (overnight). No LLM calls.
Data: the whole corpus (2,941 items), each item linked on its own (topic forced to `economia` so every rule can fire).
Script: `experiments/g3/context_eval.py` (copy of the scratch script).

## Approaches

- Rules: the keyword rules of `pipeline/context.py` (inflation, unemployment, GDP, exports, quakes with date and location checks).
- Embeddings: cosine between each news vector and five family descriptions embedded as queries ("inflación y precios al consumidor en Panamá", ...), threshold 0.5.

Every link either method produced (29 distinct items) was judged by Claude Opus: is the linked indicator pertinent context for that news item?

## Results

| Linker | Links | Correct | Precision | Recall vs all 24 correct links found |
|---|---|---|---|---|
| Keyword rules | 21 | 17 | 0.81 | 0.71 |
| Embedding similarity >= 0.5 | 13 | 12 | 0.92 | 0.50 |
| Union of both | 29 | 24 | 0.83 | 1.00 |

- Rule false positives: foreign contexts ("Reino Unido pone la mirada en Darién: crecimiento económico...", "EEUU reactiva... exportación de ganado de México") and incidental keywords ("Ministro Navarro... los economistas ven el desempleo", a tourism alliance linked to GDP).
- Rule misses: "Producto Interno Bruto de Panamá crece 6.4 %...", "Economía panameña crece 8.49 % en julio", "La economía panameña acelera...", S&P growth projections, price rises at Merca Panamá.
- Embedding misses: every unemployment item (cosine about 0.37) and the quake item; similarities are low overall (max 0.62), so a threshold is fragile.

## Verdict

- Keep explicit rules: they are explainable, the jury can read them, and they cannot invent a link from vague similarity.
- Fix the rules with what the embeddings found: add "producto interno bruto" and "economía (panameña) crece/creció/acelera" patterns for GDP; reject a Panamanian indicator when the item is about another country (the same filter the quake rule now has).
- Use embedding similarity only as an offline tool to find missing keywords, not as a linker.

## After the fixes (measured, commit `c5b3fa1`)

| Linker | Links | Correct | Precision | Recall vs the 24 correct links |
|---|---|---|---|---|
| Keyword rules, fixed | 23 | 20 | 0.87 | 0.83 |

- Gained: the three GDP headlines above; removed: the Mexico cattle-export link.
- Still wrong: "Reino Unido... Darién" (names a Panamanian region, so the other-country filter does not apply), the mining minister quoting "desempleo", a tourism alliance matching "crecimiento económico".
- Still missed: S&P rating news, a tariff advantage for agro exports, price rises at Merca Panamá (no inflation keyword).
