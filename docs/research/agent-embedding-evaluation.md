# Agent evaluation of the frozen embedding comparison

Date: 2026-10-08. The user explicitly asked Codex to perform the evaluations and waive the pending manual-review step. This is an **AI-agent judgment set**, not independent human ground truth. Human review is optional for this delivery; no human labels or results were fabricated or overwritten.

## Decision

Keep **EmbeddingGemma ONNX q4**. fp32 has a small pooled nDCG advantage, but lower precision/recall and identical sampled grouping results. Its measured peak process memory is about 46% higher. These observations do not establish a clear quality improvement that justifies replacing q4. Gemini generation and G10's model-free offline runtime stay unchanged.

The more useful next investigation is the current retrieval fusion and event boundaries, rather than replacing the embedding weights. The current BM25/RRF/cosine-gate recipe underperforms pure embeddings on this development pool, and both builds make the same nine resolved grouping mistakes. This report identifies those findings; it does not silently change the retriever, thresholds, generated content or production model.

## Coverage and procedure

Codex read every frozen input: **217 query/document judgments across 30 queries and all 50 event pairs**, for 267 submitted agent decisions. Candidate names, rankings and predictions were withheld from the input batches until judgments had been serialized. After freezing the judgments, candidate outputs were unmasked for scoring and error analysis. No historical machine labels were imported. No local judge model or paid generation API was called, and G7's reserved set was not accessed.

Relevance criteria: 2 directly concerns the requested fact/topic; 1 contributes useful context without establishing the requested fact; 0 is unrelated, a different entity/location/benefit, or a lexical collision. Examples include subadministrator versus administrator, fuel versus electricity subsidies, and a David road crash versus the Panama-David railway. Topic relevance is judged from the frozen headline and available excerpt; it does not certify every underlying claim's factual accuracy.

Event criteria distinguish one concrete incident/decision/fixture from subsequent legal acts, different games, separate dated TV episodes and recurring distributions. Original primary articles were consulted where a thin headline could not establish the event boundary. Sources used for additional adjudication are recorded per item. There are **49 resolved pairs** and **one unknown pair**: an RSE-week opening and next-day thematic report could cover the same ceremony or a later session; one video source could not be fetched and the available material did not determine it. It remains assessed-but-unknown, excluded from F1 rather than converted into a negative. All 30 query pools are fully scored.

The judgment file is bound to snapshot `0b9418e6bae9753955b9bf79c22d7529dab65a0bcb41470a48763c3a22cceccd`. [Every judgment and rationale](../../outputs/experiments/embedding-validation/agent-judgments.jsonl) has explicit `reviewer_kind=agent`, `actor=Codex (AI agent)`, timestamp, item ID and snapshot identity. [Results](../../outputs/experiments/embedding-validation/agent-results.json) also fingerprint the judgment list. Original human results remain zero judgments.

## Retrieval results

| Candidate | Precision@5 | Pooled recall@5 | Pooled nDCG@5 | Queries |
| --- | ---: | ---: | ---: | ---: |
| q4 | 0.9000 | 0.8226 | 0.9581 | 30 |
| fp32 | 0.8933 | 0.8143 | 0.9646 | 30 |
| q4 + BM25/RRF | 0.8067 | 0.7360 | 0.8819 | 30 |
| fp32 + BM25/RRF | 0.8067 | 0.7360 | 0.8851 | 30 |
| BM25 | 0.8067 | 0.7360 | 0.8851 | 30 |

The pure q4 candidate returns 135 relevant results out of 150 top-five slots; fp32 returns 134, and each hybrid/BM25 returns 121. The production-style hybrid includes its existing 0.62 cosine gate and 20-document fusion pool; the pure embedding candidate has no such gate. q4 hybrid's ordered top five equal BM25 on 26/30 queries; fp32 hybrid equals it on 25/30. This is evidence of weak semantic contribution in this configuration, not proof that all hybrid retrieval is worse. Do not calibrate the gate on reserved queries or promote a new setting from these judgments alone.

Recall is within the union of judged candidates, not full-corpus recall. nDCG uses the ideal ranking within that same judged pool. Aggregates are macro averages. The 0.0065 fp32 nDCG advantage is small and is not a statistical-significance claim; ratings come from one AI agent. The 30 public development queries and historically model-selected event pairs do not represent an unbiased production distribution.

## Grouping results

| Candidate | TP | FP | FN | TN | Resolved pairs | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| q4 | 6 | 7 | 2 | 34 | 49 | 0.5714 |
| fp32 | 6 | 7 | 2 | 34 | 49 | 0.5714 |

Grouping uses the current average-linkage threshold 0.275 and 72-hour exclusions, **without LLM overrides**. BM25 has no event-grouping score. Both candidates confuse seven distinct facts with the same event: semifinal/final stages, apprehension/provisional detention, different daily program episodes, separate reform statements, Tuesday/Friday fairs, injury-list/playoff updates and PASE-U delivery days. They split two adjudicated shared events: representatives' policing request in article/video, and the MOP funding hearing with a contemporaneous parliamentary dispute. Changing q4 to fp32 does not fix these mistakes in this sample.

Source checks supporting ambiguous boundaries: [Curundu El Amanecer fire](https://www.tvn-2.com/nacionales/incendio-curundu-deja-23-familias-miviot-evalua-soluciones_1_2263728.html) versus [La Macarronera fire](https://www.tvn-2.com/nacionales/incendio-barraca-la-macarronera-calle-29-bomberos-panama-fuego_1_2262805.html) establishes distinct places/incidents; the [water-security article](https://www.tvn-2.com/nacionales/estres-hidrico-contaminacion-amenazan-seguridad-agua-panama-medio-ambiente_1_2262571.html), [inflation article](https://www.tvn-2.com/nacionales/panama-nueva-amenaza-inflacion_1_2261728.html) and [policing-request article](https://www.tvn-2.com/nacionales/representantes-corregimientos-piden-mayor-presencia-policial-inseguridad_1_2259896.html) contain the respective video headline. The [MOP funding request](https://www.tvn-2.com/nacionales/mop-solicita-43-1-millones-comision-presupuesto-obras-en-ejecucion_1_2264626.html) and [parliamentary dispute](https://www.tvn-2.com/nacionales/diputada-chong-benicio-robinson-chocan-comision-presupuesto-asamblea-nacional_1_2264696.html) concern the same funds-transfer hearing and Randolph works; treating the dispute as a same-day reaction is an agent adjudication, not a quoted source label.

## Reproduce and inspect

```powershell
whoami compare-embeddings score-agent --directory outputs/experiments/embedding-validation
whoami compare-embeddings review --directory outputs/experiments/embedding-validation --port 8766
```

The review page folds the optional human form and links to `/agent-results`. It computes that report from the validated agent judgment file at startup; it does not trust arbitrary saved report JSON as human evidence. The agent scoring command writes only `agent-results.json`. It never opens or alters `human.sqlite3` or `human-results.json`. No further manual labels are required to complete this authorized agent evaluation.
