# Issue #40: correction evidence

Reviewed baseline: `957c3642e7143f1ab6a2c134e5e2e1ed93b9f8b7`.
Final application code: `de88091d9a1ed00e7c4bcf15afb619ee7de54d1f`.
The issue contains 15 unique defects; S02/E03 and S04/E04 are shared findings.

## Requirement coverage

| Issue item | Implemented behavior | Public regression boundary |
| --- | --- | --- |
| S01 | Regeneration carries previous cases/bindings/history; unchanged bound content retains its cycle; changed/withdrawn content retires decisions with the original case/group/sources. TVN reference changes also revoke approval. Exports retain history through fresh SQLite imports. | `test_generation_run`, `test_generation_end_to_end`, `test_backend`, `test_backend_export` |
| S02/E03 | Source passages appear only in the user data message; entailment system instructions remain fixed. | `test_generation_entailment::test_source_instructions_never_enter_the_entailment_system_message` |
| S03 | Preserve signed decimals, Unicode minus and spoken negatives; opposite-sign official claims fail. Existing multipliers and written coefficients remain supported. | `test_generation_verifier`, `test_generation_query_box` |
| S04/E04 | Bind cache to texts, encoder identity, dimensions and text recipe; check vector shape, finiteness and checksum. Opaque encoders do not silently share persistent vectors. | `test_generation_evidence_index`, `test_embeddings` |
| S05 | Stage all WordPress pages and categories before replacing the snapshot. Initial/later download failures preserve posts, categories and fetch logs; successful refresh removes obsolete pages. | `test_news` |
| S06 | Partition average-linkage candidates by hard time/cannot-link membership; preserve all sources and the exact 72-hour boundary. | `pipeline/test_grouping` |
| S07 | New versions require literal values and scopes, including mixed words/numbers. Equivalent numeric expressions do not fabricate conflicts; meaningful qualitative differences remain distinct. | `test_generation_query_box`, `test_version_citations`, `test_generation_verifier` |
| S08 | Explicit pinned `download-model` command, offline check, partial-download resumption and documented setup. | `test_embeddings` |
| S09 | Separate chat/embedding caches by endpoint; provider identities are hashed in the usage ledger without exposing credentials. | `test_llm` |
| E01 | Compare external news with TVN coverage. Recognize exact headlines despite different descriptions; retain cited potential updates; partly covered groups report unverified novelty with N=0. Covered groups are absent from the main inbox/new generation. | `pipeline/test_run`, `test_backend`, `test_generation_end_to_end` |
| E02 | The model selects accepted claim IDs; code renders factual fields with types/attribution. Saved new drafts require compositional references; inventions, canary text and over-limit drafts are rejected without discarding valid claims. | `test_generation_case_files`, `test_generation_verifier`, `test_generation_run` |
| E05 | Explicit Panama news retains relevant official context when another country is mentioned; foreign-only news remains excluded. | `pipeline/test_context::test_explicit_panama_trade_keeps_context_when_counterparty_is_foreign` |
| E06 | Render absent, partial and complete source coverage correctly; `todos` does not become five days. | `test_backend_quality::test_quality_screen_reports_all_missing_days_without_counting_a_string` |
| E07 | Validate HTTP/HTTPS centrally before alias deduplication; malformed or unsupported URLs cannot consume valid articles. RSS, sitemap and WordPress exclusions are counted in quality reports. | `test_news` |
| E08 | Notion mirror records G7 merge #37, ten completed owner reviews and 8/10 support, preserving historical G8 evidence and unresolved G7 criteria. | `docs/notion/06-pruebas-y-metricas.md` inspected against the merged commit and recorded review files |

The original defects and additional integration variants were reproduced red
before their fixes. The first full run caught the public generation-loader gap:
746 passed and eight failed. Its records remain in
`outputs/validation/issue40/attempt-1/`; subsequent corrections were verified at
the failing public boundary before repeating the full suite.

## Automated validation

Final local run: **768 passed, zero failed, 12 warnings, 36.47 seconds**.
Warnings identify the existing 22 undated news rows retained in the CSV and
excluded from grouping. Python source/scripts compile successfully; locked
dependency synchronization and wheel build pass. Evidence:

- `outputs/validation/issue40/verified-suite/pytest.xml` and `pytest.log`.
- `outputs/validation/issue40/verified-suite/http-runtime.json`: actual HTTP
  screens, restart, persistent human decisions and export/reload checks.
- `uv sync --locked --link-mode copy` and `uv build --wheel --out-dir dist/issue40`.

GitHub's `G5 validation` matrix separately runs the locked suite and wheel build
on Windows and Linux. Its status must be green before integration into `prod`.

## Corpus and generation captures

`production-reviewed/metrics.json` runs the current G1 CSV through the production
offline AI configuration: **3,154 dated news, 2,302 groups, 357 inbox groups and
zero TVN-only inbox groups**. Coverage is 1,945 covered, 306 without a semantic
match in the loaded snapshot, 50 unverified and one cited potential update.

The frozen 2,941-news vectors were first verified against their manifest.
Exactly 2,844 identical document texts were reused; 310 new/changed texts were
encoded locally with the pinned ONNX model. Final reruns reused this separate
vector capture only after checking the CSV hash, encoder identity and vector
bytes. The report records that reuse origin and zero newly encoded texts in the
final run. The original CSV, frozen vectors and historical outputs remain unchanged.

`live-verified/` captures two current eligible editorial packages using Gemini
3.5 Flash Lite: three accepted claims, both drafts mechanically verified, both
review states `nuevo`. The run records four cache hits and three successful
network calls across extraction, entailment and package selection. One cached
case took about 0.006 seconds; the other took 52.887 seconds including provider
and rate-limit waits. These two mixed cache/network observations are not a new
benchmark latency estimate or human support measurement.

Earlier captures remain under their separate names, including the initial
four-claim real-provider exercise and its cached recheck. Coverage-method v3
corrects the partial-coverage interpretation found during inspection of real
rankings. No source refresh, publication, new human decision or held-out access
was part of these captures.

Reproduce in new directories (the scripts reject existing destinations):

```powershell
$env:WHOAMI_EMBEDDING_THREADS = '2'
uv run --locked python scripts/validate_issue40_snapshot.py --output outputs/validation/issue40-rerun --vectors-output C:/path/to/new-vector-directory
uv run --locked python scripts/validate_issue40_live.py --snapshot outputs/validation/issue40-rerun --output outputs/validation/issue40-live-rerun --cases 2
```

The second command uses the configured Gemini credentials and shared quota/cache
controls. It requests no additional human reviews.

## Historical G7 comparison

The new replay in `outputs/validation/issue40/evaluation/` recalculates evaluation
with current retrieval/grouping code while preserving recorded generation.
The 345 proposed pair labels give unchanged embedding F1 **0.72146**, precision
**0.66387** and recall **0.79**: the bridge/cannot-link bugs are reproduced by
targeted regressions rather than an observed aggregate improvement on these
labels. Classification and captured answers also remain historical measurements.

Recorded answers stay **37/40**, with **33/33** query claim/version references
and **41/41** fiche claim references. The owner-reviewed sample remains exactly
**eight supported and two unclear, 80% over ten**. No labels or verdicts were
rewritten. G7 remains incomplete because of its human-label, reserved-evaluation
and original support-target requirements; #40 does not close #25. The private
20-query package was not read or used for tuning.

## Standards

Two independent reviewers assessed the fixed diff and all subsequent corrections.
Final Standards review at `de88091` found **no pending documented violations or
concrete heuristic smell findings**. It rechecked review ownership/history,
provider/source separation, signed numbers, model-aware caching, staged ingestion,
hard grouping, contradiction support, setup, TVN coverage and validation scripts.

## Spec

Final Spec review at `de88091` found **no pending implementation findings or
unrequested scope expansion** within the 15 corrections. Its reporting clarification
for vector reuse was applied: the final report distinguishes the 310 texts encoded
in the original capture from zero encoded during the verified reuse run.

**Review totals: Standards 0 pending; Spec 0 pending.** Platform checks and merge
status are verified separately through the pull request.
