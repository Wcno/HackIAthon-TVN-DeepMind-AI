# G7 measured development results

Status: provisional. Human topic/pair/benchmark labels and claim support reviews have not been supplied. This report does not close issue #25.

Run: 40 development queries on 3,727 evidence records (2,941 frozen news items plus official and synthetic evaluation sources). The 20 held-out queries were not read or used for tuning. Gemini 3.5 Flash Lite generation used the configured API. Original cold-run timings and tokens are retained; rescoring made no additional model calls.

| Measurement | Result |
| --- | --- |
| Query correctness | 37/40 (92.5%) |
| Correct abstentions | 7/7 |
| False abstentions on all answerable questions | 1/27 |
| False abstentions on supported questions only | 0/20 |
| Adversarial safety | 6/6 |
| Literal references in structured case-file claims | 41/41 |
| Answer-level literal references | 21/21; does not establish per-factual-claim coverage |
| Query factual-claim coverage | Unavailable: free text has no exhaustive claim-to-citation map |
| Generation wall time, median / p95 | 1.443 s / 16.803 s |
| Provider calls / network tokens | 70 / 73,614 |
| Input / output tokens | 53,297 / 20,317 |
| API failures | 0 |
| Automated tests | 671 passed |
| T01-T10 local checks | 10/10 passed; G10 event/Notion delivery remains separate |

## Baselines

| Method | Recall@8 (micro) | Retrieval median | Retrieval p95 |
| --- | --- | --- | --- |
| BM25 | 97.37% (111/114) | 15.64 ms | 33.53 ms |
| EmbeddingGemma | 100.00% (114/114) | 297.47 ms | 512.58 ms |
| Hybrid RRF | 100.00% (114/114) | 311.35 ms | 530.77 ms |

Recall uses 29 queries with relevant-source labels, repeated three times; the numerator and denominator include these repetitions. Retrieval timings include query embedding, exclude warm-up/index setup, and use the same queries and corpus for all methods.

| Task | Keyword baseline | Embeddings |
| --- | --- | --- |
| Topic macro-F1, 300 proposed labels, 5-fold CV | 0.4513 | 0.8035 |
| Same-event F1, all 345 proposed pairs | 0.3167 | 0.7215 |
| Same-event precision / recall | 0.9500 / 0.1900 | 0.6639 / 0.7900 |

Embeddings recover the one source missed by BM25 and improve topic/grouping F1 on the proposed labels. BM25 is much faster and already recovers most expected evidence. The keyword grouping baseline has higher precision, while embeddings gain recall and introduce more false merges. These results do not justify using IA for every task. Topic and pair quality is exploratory until human labels are imported; model selection also used this development labeling pool.

## Failures requiring review

- D-A05: the proposed bare anchor is 151, while the answer gives the source-backed exact amount 151.5 million. The current scoring conservatively records this as a failed anchor; human adjudication must decide the approximate-title criterion.
- D-C01: the answer returns the second-quarter growth figure but does not expose the other period/version requested by the ambiguous question.
- D-C06: the system abstains despite retrieved conflicting transit announcements. This is counted as a false abstention.

Human support is unavailable (0 reviewed claims). At least 30 unique generated claims and at least 90% supported verdicts are required before completion. Review packets contain 41 generated claims and the full sources. Reserved material stays at the local jury-package path outside the checkout.

Source artifacts: `outputs/evaluation/g7-live/` retains original API results; `outputs/evaluation/g7-final/metrics.json` contains corrected scoring and the test matrix. The configured API key was checked against saved artifacts and is absent.

Environment: Windows-11-10.0.26200-SP0, Python 3.14.3, 20 reported CPUs; ONNX uses 2 threads. Generation latency includes rate-limit waits; monetary cost was not inferred.
