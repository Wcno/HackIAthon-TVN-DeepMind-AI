# G7 measured development results

Status: provisional. Ten claims were reviewed by the user in this conversation: eight supported and two unclear. Human topic/pair/benchmark labels remain unavailable. This report does not close issue #25.

Run: 40 development queries on 3,727 evidence records (2,941 frozen news items plus official and synthetic evaluation sources). The 20 held-out queries were not read or used for tuning. Gemini 3.5 Flash Lite generated structured query claims using the configured API. Query wall times and provider usage from that capture are retained; rescoring made no additional model calls. Case-file generation reused the earlier verified cache.

| Measurement | Result |
| --- | --- |
| Query correctness | 37/40 (92.5%) |
| Correct abstentions | 7/7 |
| False abstentions on all answerable questions | 1/27 |
| False abstentions on supported questions only | 0/20 |
| Adversarial safety | 6/6 |
| Literal references in structured case-file claims | 41/41 |
| Human-supported claims / reviewed claims | 8/10 (80%); two unclear verdicts remain in the denominator |
| Answer-level literal references | 21/21 |
| Query factual-claim literal-reference coverage | 33/33: 23 individual claims plus 10 contradiction versions |
| Generation wall time, median / p95 | 1.420 s / 2.930 s, across 40 queries |
| Provider completions | 70: 30 network calls and 40 cache hits |
| Network tokens | 46,280 |
| Input / output tokens, including cached completions | 55,937 / 22,227 |
| API failures | 0 |
| Automated tests | 688 passed; wheel build passed |
| T01-T10 local checks | 10/10 passed; G10 event/Notion delivery remains separate |

## Baselines

| Method | Recall@8 (micro) | Retrieval median | Retrieval p95 |
| --- | --- | --- | --- |
| BM25 | 97.37% (111/114) | 6.76 ms | 27.94 ms |
| EmbeddingGemma | 100.00% (114/114) | 64.67 ms | 443.75 ms |
| Hybrid RRF | 100.00% (114/114) | 70.37 ms | 514.15 ms |

Recall uses 29 queries with relevant-source labels, repeated three times; the numerator and denominator include these repetitions. Retrieval timings were measured again in the final replay at `2026-10-08T03:47:53.363058+00:00`; they include query embedding, exclude warm-up/index setup, and use the same queries and corpus for all methods. Generation timings above are preserved from the structured API capture, rather than replaced with replay timings.

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

The user requested exactly ten claim reviews, presented one by one in packet order. The results are eight supported and two unclear, saved with source-bound hashes, UTC timestamps and the conversation's reviewer identifier in `outputs/evaluation/human-reviews/claims.jsonl`. Unclear claims are `CASO-7eec9567e8/A-2` (workshop dates/participants) and `CASO-f15debf340/A-3` (tension in the legislative session). No verdict was inferred or replaced, and the review stops at ten as requested. This convenience sample covers four case files and must not be generalized to all 41 generated claims. The original G7 evaluator retains its 30-claim/90% completion criteria, which this limited sample does not satisfy. Topic and pair files are deliberately empty because no such decisions were given. Review packets contain 41 generated claims and the full sources. Reserved material stays at the local jury-package path outside the checkout.

The user also specified TVN's editorial purpose: discover news from other sources that TVN has not yet published, with attractive, clear and factual titles. These claim-support reviews include existing TVN stories, so they do not demonstrate discovery of news absent from TVN. One workshop title was judged insufficiently engaging despite its supported facts. The instructions are preserved in `outputs/evaluation/human-reviews/editorial-context.json`; novelty against TVN coverage and headline appeal require distinct evidence from factual support.

Source artifacts: `outputs/evaluation/g7-structured-live/` retains the structured API capture; `outputs/evaluation/g7-final/metrics.json` contains corrected scoring and the final test matrix. Contradiction citations were enriched deterministically from explicit literal source fields, with no additional API calls. The configured API key was checked against saved artifacts and is absent.

The earlier legacy capture remains in `outputs/evaluation/g7-live/`: 70 network calls, 73,614 network tokens, query median 1.443 s and p95 16.803 s. It predates exhaustive structured query claims. Its complete source fingerprint was added retrospectively through an audit against immutable commit `b64fe80`, explicitly documenting canonical equivalence and LF/CRLF differences. These historical results were not overwritten or pooled with the new run. Across both actual captures, 100 network calls consumed 119,894 network tokens; the final replay added zero.

Environment: Windows-11-10.0.26200-SP0, Python 3.14.3, 20 reported CPUs; ONNX uses 2 threads. Generation latency includes rate-limit waits; monetary cost was not inferred.
