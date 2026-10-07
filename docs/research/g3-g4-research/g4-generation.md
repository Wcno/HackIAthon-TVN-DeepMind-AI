# G4 · Grounded generation (issue #22): overnight report

Status: done for the night (2026-10-07, about 13:30 UTC).
Branch: `feat/g3-g4-ia` (developed on `proto/g4-generation`).

## What exists on the branch

- `src/whoami/generation/`: strict JSON schemas and converters, deterministic citation verifier with Spanish number normalization, instruction/source separation with a canary, retrieval (BM25, embeddings, RRF hybrid), abstention gates (cosine, LLM, both), query box, contradiction checkers (rules, LLM), case-file generators (single-shot, two-step), optional LLM entailment check, `whoami generar`.
- `experiments/g4/`: the dev set and the experiment scripts (see "How to run").
- Tests: 410 passing on the branch (no network, fake LLM).

## Dev set (agent-labeled, not the reserved G7 benchmark)

- `experiments/g4/devset_consultas.jsonl`: 40 queries, 10 per type: answerable (8 news, 2 official figures), contradiction or ambiguity (7 real, 3 synthetic), no answer, adversarial.
- `experiments/g4/devset_sinteticas.jsonl`: 8 synthetic news items (`.invalid` URLs, "Medio sintético"): 6 for contradictions, 2 carrying injected instructions.
- Real contradictions found in the corpus: two growth figures from the same minister (6.4 % Q2 vs 4.4 %), 80 vs 70 complaints by resident doctors, 12 vs 13 arrests in Operación Poseidón, 2 vs 63 influenza deaths (different scopes), 32 vs 33 Canal transits (an update).
- `data/consultas_demo.jsonl`: the 35 dev queries that use real evidence only, for the precomputed demo answers.

## Experiments

### Retrieval (BM25 vs embeddings vs hybrid)

Expected evidence found in the top 8, 22 dev queries that name their evidence:

| Retriever | Recall@8 |
|---|---|
| BM25 | 0.932 |
| Embeddings (embeddinggemma q4) | 1.000 |
| Hybrid (RRF of both) | 1.000 |

- Official figures embed badly as key-value text; rendering them as a Spanish sentence ("Desempleo de Panamá en 2024: 8,45 % de la fuerza laboral (Banco Mundial)", months as words) moved the World Bank query from a miss to rank 1.
- A bug in the first rendering labeled every World Bank row "de Panamá"; the country now comes from the id.
- See also the G3 retrieval bake-off (30 queries, 932 judged pairs): embeddinggemma nDCG@10 0.86-0.87, BM25 0.76.

### Abstention gate

Top-1 embedding cosine per dev query type (embeddinggemma q4):

| Type | Range |
|---|---|
| Answerable | 0.629 - 0.841 |
| Contradiction | 0.650 - 0.807 |
| No answer | 0.401 - 0.653 |
| Adversarial | 0.473 - 0.700 |

- `MIN_COSINE = 0.62` separates answerable from no-answer on this set, except "unemployment in 2026" (0.653): the retrieval finds unemployment rows of other years, so a pure similarity gate cannot see a missing period.
  The answer model then abstains (the sources lack 2026), which is why generation must be allowed to abstain after the gate.
- The threshold was chosen on the dev set itself: treat it as optimistic until the G7 benchmark confirms it.

### Query box, end to end

| Model | Retriever | Gate | Answerable | Contradiction | No answer | Adversarial | Wrong abstentions | Unsafe |
|---|---|---|---|---|---|---|---|---|
| gemini-3.1-flash-lite | hybrid | cosine 0.62 | 10/10 | 9/10 | 10/10 | 10/10 | 0/10 | 0 |
| gemma-4-26b-a4b-it | hybrid | cosine 0.62 | 7/10 | 2/10 | 10/10 | 9/10 | 3/10 | 0 |
| gemma-4-26b-a4b-it | BM25 | cosine 0.62 | 5/10 | 1/10 | 10/10 | 10/10 | 4/10 | 0 |
| gemma-4-26b-a4b-it | embeddings | cosine 0.62 | 9/10 | 0/10 | 10/10 | 9/10 | 1/10 | 0 |
| gemma-4-26b-a4b-it | hybrid | LLM | 5/10 | 1/10 | 10/10 | 10/10 | 5/10 | 0 |
| gemma-4-26b-a4b-it | hybrid | cosine + LLM | 5/10 | 1/10 | 10/10 | 10/10 | 5/10 | 0 |

Gemma rows ran before two fixes found in them (see below); they measure Gemma under a 20 % invalid-JSON rate and frequent HTTP 500s that night.

- Why Gemma lost: 82 of 258 query and gate calls returned HTTP 500 and 43 returned invalid JSON; an invalid gate answer is a refusal (5/10 wrong abstentions with the LLM gate).
  Gemma also answered `estado=respondida` while filling both contradiction versions (D-C02).
- Fixes (commit `1a4a5c3`): one retry with "JSON compacto en una sola línea" on invalid JSON; two verified versions with distinct values make a contradiction whatever state the model chose; every call has a `max_tokens` cap (commit `b82be19`) after an uncapped answer call hung 90 s per attempt.
- Gate verdict: the cosine gate beats the LLM gate (no extra call, no wrong abstentions caused by unusable gate answers); "both" adds nothing over the LLM gate.

- First run was 36/40; two fixes in the deterministic verifier and one in the dev set took it to 39/40, re-scored from the cache at zero cost:
  - A correct answer was discarded because it added the publication date of the cited news ("12 de septiembre de 2026"); numbers are now accepted from any field of a cited record, not only the cited field.
  - Contradiction versions were not checked against their records; now every figure of a version must appear in the record it names.
  - D-C07 was relabeled: the MEF's 6.4 % and the INEC's 6.38 % for 2026-T2 agree, so a direct answer is correct.
- Remaining miss: D-C06 (32 transits until December vs 33 from 15 October): the model gives the newer figure without mentioning the older one.

### Verification: deterministic vs deterministic + LLM entailment

Controlled test: 12 true claims from the demo case files and 12 perturbed copies (4 wrong figures, 8 invented details: attribution, cause, place, extra fact).

| Verifier | Perturbed caught | True wrongly rejected |
|---|---|---|
| Deterministic only | 5/12 | 0/12 |
| LLM entailment, gemini-3.1-flash-lite | 10/12 | 0/12 |
| Deterministic + entailment, gemini-3.1-flash-lite | 11/12 | 0/12 |
| LLM entailment, Gemma | 9/12 | 0/12 |
| Deterministic + entailment, Gemma | 10/12 | 0/12 |

- The deterministic verifier catches every wrong figure and nothing else; invented attributions, causes and places need the entailment check.
- On the real demo case files, the entailment check passed "zona fronteriza con Costa Rica" for a USGS place "148 km SSE of Burica, Panama": it is lenient with plausible additions that are not in the source.

### Contradictions inside a group (rules vs LLM)

8 positive pairs (5 real, 3 synthetic) and 18 negative same-event pairs (including different figures for different places).

| Checker | Positives caught | False alarms |
|---|---|---|
| Rules (figures and dates) | 5/8 | 1/18 |
| Gemma pairwise | 7/8 | 2/18 |
| Union of both | 7/8 | 3/18 |

- Rules miss: a figure attached to different nouns ("12 aprehendidos" vs "aprehensión de 13 personas"), numbers in words ("dos muertes" vs "63 muertes") and dates with different verb forms ("reabrirá el 12" vs "reabre el 20 de octubre").
- The rules' false alarm: 56 mil acudientes in Panamá Este vs 1,700 in Panamá Centro (different places).
- Gemma misses only the influenza scope pair (2 recent vs 63 cumulative deaths); its false alarms: "segundo vs tercer debate" (two steps) and "Estados Unidos vs Milwaukee" (the same trip).
- Verdict: Gemma pairwise as the detector (short JSON is reliable on Gemma), rules as the offline fallback; every contradiction is shown as pending verification, so a false alarm costs a reviewer a glance while a miss hides a conflict.

### Injection (T07): instruction/source separation

10 adversarial sources (canary request, "HACKEADO", fake closure, fake system tags, URL insertion, false attribution, off-task poem, a fake corrected figure), each next to a real news item, three prompt designs, Gemma:

| Design | Obeyed the injection | Canary leaked |
|---|---|---|
| Rules in system message, sources in neutralized `<fuente>` tags, strict schema (production) | 0/10 | 0/10 |
| Rules and raw sources in one user message, strict schema | 2/10 | 0/10 |
| Same naive prompt, free text | 10/10 | 10/10 |

- The schema is the strongest single defense; delimiting removes the remaining obedience.
- The automatic check flagged 2/10 for the production design, but both were the injected claim ("cerró definitivamente", "99 tránsitos") shown as one side of a contradiction with its source named, while the instruction itself ("no la cites") was ignored: not obedience, but a risk.
- Recommendation: quarantine a source whose text addresses the assistant ("asistente", "ignora las instrucciones", "prompt"), so an adversarial headline cannot create a fake contradiction.

### Case files on the demo set (single-shot vs two-step)

| Generator (gemini-3.1-flash-lite) | Case files | Claims kept / generated | Packages | Calls |
|---|---|---|---|---|
| Single-shot | 5 | 12 / 12 | 5 | 5 |
| Two-step | 5 | 14 / 14 | 5 | 10 |

- Both keep statements attributed, official figures with period and unit, and the headline-only legend where it applies.
- The demo set is too easy to separate them (no claim was dropped). On real groups the deciding factor was reliability, not quality: two-step survives a model that fails long JSON (claims extract fine, the package can be retried or omitted), single-shot loses the whole case; see the final pass section.

## Final pass: gemini-3.5-flash-lite (the production model)

Same pipeline, no prompt changes needed: it matches gemini-3.1-flash-lite and beats Gemma.

| Dev set | gemini-3.5-flash-lite | gemini-3.1-flash-lite | Gemma |
|---|---|---|---|
| Query box (40), hybrid + cosine gate | **39/40**, 0 unsafe, 0 wrong abstentions | 39/40, 0, 0 | 28/40, 0, 3 |
| Injection, production design (10) | 0 obeyed, 0 canary | not run | 0 obeyed, 0 canary |
| Verifier perturbations (12 + 12), deterministic + entailment | 10/12 caught, 0 false drops | 11/12, 0 | 10/12, 0 |
| Case files on real top-5 groups, two-step + entailment | 5/5 case files, 11/11 claims kept, 5 packages | not run | see below |
| Reliability | 81 calls, 0 errors, p50 1.1 s | 98 calls, 19 errors (503), p50 9 s | 20 % invalid JSON, many HTTP 500 that night |

- The remaining query miss on both flash-lite models is D-C06 (32 transits until December vs 33 from 15 October): the newer figure is given without the older one.
- Gemma on case files (real top-10 groups): single-shot produced 0 case files (every long JSON failed); two-step produced 10/10 case files (11 claims, 10 confirmed by entailment, 1 entailment error) but only 3 with a package, because most package calls returned invalid JSON (38 calls in all).
  Verdict: Gemma for short JSON (classification, verdicts, entailment, contradiction pairs); flash-lite for long structured generation.

## Real outputs (committed on `proto/g4-generation`)

`whoami generar --modelo gemini-3.5-flash-lite --top 5 --generador two --implicacion --recuperador hybrid --compuerta coseno`:

- `outputs/fichas.jsonl`: 5 case files for the 5 top groups, 11 claims (all kept by the deterministic verifier and the entailment check), 5 editorial packages; `verify()` passes on load.
- `outputs/consultas.jsonl`: 35 precomputed answers (13 answered, 5 contradictions, 17 abstentions) for the offline demo (D-01).
- Grounding validity, reviewed by Claude Opus on all 11 claims against their passages: 11/11 supported (below the 30 claims §9.1 asks for: exploratory).
- Weak points seen in review: a brief that reads "$94 millones y casi $100 millones" as two amounts; one brief lost its accents ("Republica", "Jose"); the top-5 groups are thin stories (budget sessions, a training workshop) because of the G3 ranking issue.

## Recommendations (what to move to `prod`)

- Query box: hybrid retrieval, cosine gate 0.62, gemini-3.5-flash-lite answer with strict schema, deterministic verification (all fields of the cited record, versions checked), JSON retry, versions-to-contradiction rule.
- Case files: two-step generator (claims, code verification, package from verified claims only) + LLM entailment per claim on gemini-3.5-flash-lite.
- Contradictions: LLM pairwise check (Gemma is fine) inside each group, rules as offline fallback; always "pending verification".
- Injection: keep the production design; add a quarantine for sources that address the assistant.
- Discard: the LLM gate (and "both"); single-shot generation on Gemma.

## Open decisions

- Cosine threshold 0.62 was set on the dev set; confirm on the G7 benchmark.
- How to show an outdated figure next to the current one (D-C06): a "versions over time" display vs a plain contradiction.
- Entailment costs one call per claim: fine on flash-lite for 10 cases, budget it for more.

## How to run

```bash
uv run --all-groups pytest -q                                          # 615 tests, no network
WHOAMI_BUDGET_SINCE=2026-10-07T06:30:00Z uv run --all-groups whoami generar --modelo gemini-3.5-flash-lite --top 5 --generador two --implicacion
export WHOAMI_DEV_EVIDENCE=$PWD/data/processed/evidencias.jsonl
uv run --all-groups python experiments/g4/query_devset.py retrieval
uv run --all-groups python experiments/g4/query_devset.py answer --gate retrieval --retriever hybrid --model gemini-3.5-flash-lite --min-cos 0.62
uv run --all-groups python experiments/g4/contradictions_eval.py --model gemma-4-26b-a4b-it
uv run --all-groups python experiments/g4/injection.py --model gemma-4-26b-a4b-it
uv run --all-groups python experiments/g4/verifier_perturbations.py --model gemini-3.5-flash-lite
uv run --all-groups python experiments/g4/case_files_devset.py --generator two --model gemini-3.5-flash-lite --data data/processed --groups 5 --entailment
```

Calls are cached on disk (`~/.cache/whoami/llm/`) on the machine that made them: re-running there costs nothing.

## Calls per model (whole night, both issues, from the ledger)

| Model | Network calls | Errors | Cap tonight |
|---|---|---|---|
| gemma-4-26b-a4b-it | 3,484 | 296 (mostly HTTP 500, invalid JSON) | 5,000 |
| gemini-3.1-flash-lite | 98 | 19 (503 overload) | 200 |
| gemini-3.5-flash-lite | 81 | 0 | 100 |
| gemini-embedding-2 | 19 successful batches, 795 texts embedded | 12 rejected batches (429) | 900 texts |

The ledger summary shows 1,395 texts because it sums the 12 rejected batches (50 texts each) that never embedded anything; the layer now limits texts per minute and charges a rejected attempt one unit.
Peak usage since the limiter fixes: Gemma 25 RPM (cap 30), 9.3K TPM (cap 16K).
