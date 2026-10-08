# G7: reproducible evaluation

[G7 / issue #25](https://github.com/Wcno/hackiaton-whoamisfc/issues/25) runs with one command:

```powershell
$env:WHOAMI_EMBEDDING_THREADS = '2'
uv run --locked whoami evaluar --mode live --human-reviews C:/path/to/reviews
```

Download the pinned EmbeddingGemma ONNX model first. Configure `GEMINI_API_KEY`
in the environment or `.env`. Generation uses the shared `whoami.llm` client,
cache, ledger and limits. The command saves answers, case files, rankings,
predictions, metrics, pytest results and real HTTP T10 evidence under
`outputs/evaluation/g7/`. Provider failures remain distinct from correct
abstentions. Credentials are never included in artifacts.

To evaluate existing product answers without Gemini calls:

```powershell
uv run --locked whoami evaluar --mode recorded
```

Recorded mode measures retrieval and validates archived answers whose questions
match exactly. Missing answers remain in the denominator. Original generation
latencies and tokens are unavailable; file-reading time does not replace them.

To apply reviewed labels or revised scoring to a captured run while preserving
its original token usage and generation timings:

```powershell
uv run --locked whoami evaluar --reuse-generation outputs/evaluation/g7-live --output outputs/evaluation/g7-final --human-reviews C:/path/to/reviews
```

The replay checks benchmark, evidence and vector hashes, verifies query identity,
and makes no model calls. Its report identifies the original run. The default
command runs the full test suite. Exit code `0` means completion prerequisites
passed; `2` means evidence or acceptance requirements remain incomplete.
`--skip-tests` is available for iteration and cannot satisfy G7 acceptance.

## Corpus and held-out isolation

Evaluation uses the frozen G3/G4 corpus, `data/processed/evidencias.jsonl`, and
vectors aligned to its 2,941 news IDs. The newer G1 news CSV is a different
snapshot: its row positions are never paired with these older vectors. The
loader checks SHA-256, model revision, dimensions, finite values and exact ID
coverage. Verified news vectors are reused for identical text; official and
synthetic sources are encoded with the same pinned model.

Synthetic evaluation sources have `N-syn*` IDs and `.invalid` URLs. They stay
outside product evidence and only enter the evaluation index. Benchmark queries,
expected answers and labels never enter retrieval documents or generation
prompts. Evaluation caches stay outside the checkout; their identity includes
source contents, model revision and news-vector bytes.

There are 60 queries: 30 supported, 10 contradictions/ambiguities, 10 unanswerable
and 10 adversarial. Development contains 40 (20/7/7/6); the held-out package
contains 20 (10/3/3/4). Both sets have distinct queries. Held-out questions and
their preparation script stay outside Git at
`~/.cache/whoami/evaluation/g7-reserved/`. The public manifest contains only
counts, distribution and the package SHA-256. It is frozen before tuning.

The default run never opens that package. The jury can explicitly select it:

```powershell
uv run --locked whoami evaluar --mode live --reserved C:/path/to/benchmark.jsonl --output outputs/evaluation/jury
```

Do not regenerate held-out cases after tuning. Machine-proposed benchmark
expectations remain provisional until a human reviews them.

## Methods and measurements

| Task | Measurement |
| --- | --- |
| Retrieval | BM25, embeddings and RRF fusion on identical sources and questions; macro/micro recall@8 and failed IDs. |
| Classification | Keywords versus embedding logistic regression; 5 stratified folds, seed 7, without training on the evaluated fold. Seven-class macro-F1, per-class scores and correct/total. |
| Grouping | Near-identical titles/time window versus production average linkage/72-hour embeddings, without new live LLM overrides. Precision, recall and F1 on all 345 pairs. Label 2 is positive; 0 and 1 are negative, never discarded. |
| Answers | Expected state, factual anchors and adversarial checks; correct/total including missing outputs. Bare numeric anchors match written coefficients: 32 matches 32 million, while 4 does not match 5.4. |
| Abstention | Correct refusals on unanswerable cases; false refusals on every case whose accepted states exclude abstention, including contradictions. Supported-only false refusals are reported separately. |
| Citations | Literal-reference coverage per structured case-file claim, answer-level references and contradiction-version references. These are distinct from semantic support. |
| Query claim coverage | Unavailable when free-text answers share citations without an exhaustive claim-to-citation map. Answer-level reference coverage must never be called 100% factual-claim coverage. |
| Human support | Supported unique claims / reviewed claims, sample size and review errors. Minimum 30 claims, target 90%; both gate completion. |
| Efficiency | Median and nearest-rank p95. Retrieval includes query embedding; warm-up and index setup are separate. Generation wall time includes retrieval, gating and provider/rate-limit waits. |
| Tokens | Provider-reported usage, network calls and cache hits separately. Unknown failed-request usage and cost remain unavailable. |

Classification remains exploratory: G3 model selection used these same proposed
labels. Cross-validation prevents fitting on a test fold but does not produce an
independent model-selection test set. Editorial Precision@5 is explicitly
outside this issue's scope.

## Human review files

The existing 300 topic labels and 345 pair labels were produced by an agent.
Their provenance remains provisional until content-bound human decisions are
imported. A run writes review packets with full source content and hashes:

- `topic_review_packet.jsonl`: news and proposed topic.
- `pair_review_packet.jsonl`: both articles and proposed relationship.
- `claim_review_packet.jsonl`: generated statement, citations and complete sources.
- `benchmark_review_packet.jsonl`: question, proposed expectations, sources and corpus hash.

The `--human-reviews` folder accepts `topics.jsonl`, `pairs.jsonl`, `claims.jsonl`
and optional `benchmark.jsonl`; CSV files with the same fields are also accepted.
Topic and pair decisions have this shape:

```json
{"subject_id":"ID from the packet","subject_hash":"hash from the packet","label":"reviewed label","reviewer":"Human reviewer name","reviewed_at":"2026-10-07T15:00:00-05:00"}
```

Topics use the seven contract slugs. Pair labels are `0` (different), `1` (same
story, different event), or `2` (same event). Claim reviews replace `label` with
`verdict`: `supported`, `unsupported` or `unclear`; `note` is optional. Benchmark
reviews use `verdict: accepted`. Rejected expectations require an explicit,
versioned correction; held-out content stays frozen.

A review must match the exact subject/source bytes and have a named human and a
valid, nonfuture timestamp with timezone. Changed or unknown subjects and
repeated decisions are reported. Citation ordering and insignificant statement
whitespace cannot inflate the unique claim sample. Machine labels never count
as human review. Pair evaluation uses stable article IDs, never old row indices.

## T01–T10 acceptance

The command saves `pytest.xml` and `pytest.log`. Each acceptance entry names
concrete tests and passes only if all named checks actually ran successfully.
T01 loads invalid/missing dates and nulls alongside valid fixture records; T02
checks repetition/provenance; T03 recirculation; T04 official periods; T05
contradictions; T06 abstention; T07 instruction/source separation; T08 explained
scores and human control; T09 validated editorial packages; T10 real offline
HTTP, restart, export and persistence. Local T10 evidence is saved in
`http-runtime.json`. The event demo and its Notion evidence belong to G10.
