# Overnight summary: G3 (AI pipeline) and G4 (grounded generation)

Night of 2026-10-07 (06:30-13:30 UTC). Every item of the overnight plan is done or recorded below with a reason.
Details: [g3-pipeline/README.md](g3-pipeline/README.md) (G3) and [g4-generation.md](g4-generation.md) (G4).

## Branch and state

Everything lands in one branch, `feat/g3-g4-ia` (one PR for #21 and #22), built from three night branches: the shared LLM layer (`proto/base`), the G3 pipeline (`proto/g3-pipeline`) and G4 generation (`proto/g4-generation`).
After the experiments, the discarded approaches were removed from the code; this document and its siblings keep the comparison.

LLM answers are cached on disk under `~/.cache/whoami/llm/` of the machine that ran them: reruns there cost nothing, elsewhere they call the API again.

## Per task: recommendation, evidence, move to `prod`, discard, risks

| Task | Recommended (move to prod) | Evidence | Discard | Risks |
|---|---|---|---|---|
| Embeddings (step 0) | embeddinggemma-300m ONNX q4, committed float16 vectors + manifest, `onnxruntime` + `tokenizers` | nDCG@10 0.86 (Gemini ceiling 0.89, MiniLM 0.77, BM25 0.76); 587 MB and 30 ms/query on 2 CPU cores | MiniLM, mpnet, e5, jina-v3 (6.6 GB), Qwen3, potion (1.2-1.6 GB), q8 build, `fastembed` at runtime | No 512 MB tier fits; labels are agent-made |
| Topics | Logistic regression on embeddings + Gemma when margin < 0.35 | macro-F1 0.88 with 45 % of calls (Gemma alone 0.86, embeddings alone 0.81) | Zero-shot (0.61), centroid (0.78) | Turismo has 7 labeled examples |
| G7 baseline | Teammate's keyword classifier with no match → `sin_tema` | 0.45 vs 0.88: AI adds +0.43 | Original default to `economía` (0.36) | — |
| Grouping (T02) | Agglomerative average linkage, 72 h window, distance 0.275; Gemma verdicts on cosine 0.65-0.80 | Pairwise F1 0.835 (0.806 without Gemma); largest group 10 | Single link (0.71, chains stories), HDBSCAN (0.76), entity/number overlap | 1,552 Gemma calls per full run (offline, cached) |
| Provenance (CU-03) | Agency markers + near-identical copies take the earliest provenance | Works on fixtures; no agency marker in this corpus | — | Corpus is TVN + 6 official sources only |
| Score (T08) | Written rules with Spanish justifications, §4 weights | Visible components, version, tie-break by U then id | — | **Top-5 favors fresh budget news over big stories: get an editor's Precision@5, consider LLM-rated impact** |
| Recirculation (T03) | Metadata rule + in-group copy rule | Demo case G-006 | — | **Never fires on real data: G1 drops old republished items by original date (decision for G1)** |
| Official context (T04) | Explicit keyword rules, improved with what embeddings found; other-country filter | Precision 0.87, recall 0.83 (rules before 0.81/0.71; embeddings 0.92/0.50) | Embedding linker (fragile threshold, misses unemployment and quakes) | Only 16 groups get context |
| Retrieval (G4) | Hybrid BM25 + embeddings (RRF), official figures rendered as Spanish sentences | Expected evidence in top 8: 1.00 (BM25 0.93) | — | Small dev set (22 queries) |
| Abstention (T06) | Cosine gate 0.62 + model may abstain | 10/10 no-answer abstained, 0 wrong abstentions (flash-lite) | LLM gate and "both" (unusable gate answers become refusals) | Threshold set on the dev set |
| Query box (CU-04) | Strict schema, deterministic verification on every field of the cited record, versions checked, JSON retry | **gemini-3.5-flash-lite 39/40**, 0 unsafe (3.1-flash-lite 39/40, Gemma 28/40) | — | Outdated figure shown without the older one (D-C06) |
| Generation | Two-step (claims → code verification → package from verified claims) | 5/5 real case files, 11/11 claims supported on review; survives models that fail long JSON | Single-shot (on Gemma 0/10 case files) | Top groups are thin stories (ranking) |
| Verification | Deterministic + LLM entailment per claim | 10-11/12 perturbations caught, 0 true claims dropped (deterministic alone 5/12) | Deterministic only | One call per claim; lenient on plausible additions |
| Contradictions (T05) | LLM pairwise inside groups, rules as offline fallback, always "pending verification" | Gemma 7/8, 2/18 false alarms (rules 5/8, 1/18) | Union (no gain) | Scope differences (2 vs 63 deaths) missed |
| Injection (T07) | Rules in system message, neutralized `<fuente>` tags, strict schema, canary | 0/10 obeyed, 0 leaks (naive free text: 10/10 obeyed and leaked) | — | An adversarial headline can become a fake contradiction version: quarantine sources that address the assistant |
| Model choice | Gemma for short JSON (topics, verdicts, entailment, contradiction pairs); gemini-3.5-flash-lite for answers and packages | flash-lite 3.5: 81 calls, 0 errors, p50 1.1 s; Gemma tonight: ~20 % invalid JSON on long outputs, many HTTP 500 | gemma-4-31b, gemini-3.8-flash | Free-tier limits are per project and shared |

## Skipped or partial, with reason

- Gemma-only runs of case files on real groups: measured (0/10 single-shot, packages 3/22), then generation moved to flash-lite; not a gap, a finding.
- Contradiction checker on gemini-3.5-flash-lite: not run to stay under its 100-call cap (81 used); it is measured on Gemma, where short JSON is reliable.
- Precision@5 of the ranking: needs an editor's independent pick, not an agent's; recorded as the main open risk.
- Human review of the labeled sets (300 topics, 345 pairs, 932 relevance judgments, 40 dev queries): all agent-made, marked "pendiente de revisión humana".

## First things to do in the morning

1. Review the ranking with an editor (Precision@5) and decide the impact rule.
2. Decide with G1 whether to keep republished old items (T03 on real data).
3. Human-review a sample of the labeled sets before quoting numbers to the jury.
4. Review and merge the `feat/g3-g4-ia` PR.

## Calls tonight (from the ledger)

Gemma 3,484 (cap 5,000), gemini-3.1-flash-lite 98 (cap 200), gemini-3.5-flash-lite 81 (cap 100), gemini-embedding-2 795 texts embedded (cap 900).
Peak Gemma usage after the limiter fixes: 25 RPM of 30 and 9.3K TPM of 16K; two peaks above the limit happened before the fixes (32-39 RPM, 14.7K TPM) and were the reason for them.
