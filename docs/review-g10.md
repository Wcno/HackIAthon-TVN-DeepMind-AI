# G10 review

Baseline: prod commit `11538206dc699699f54c11b5f33b86efa59b9cc1`.
Implementation reviewed: `37cbf29` and `810f5c5` on `feat/g10-offline`.
Two independent reviewers examined Standards and Spec before publication.

## Standards

**0 remaining findings.** Python naming, Spanish editorial/wire fields, G2
validation, local assets and separate SQLite persistence follow the documented
rules. All twelve Fowler smell heuristics were considered without actionable
findings. Runtime retrieval and packaging metadata checks protect different
boundaries; packaging additionally requires an ordered text fingerprint.

The refresh checks historical vector hashes and model identity, reuses only exact
ID/text matches, and preserves existing float16 values through its float32
intermediary. The historical embedding recipe and truncation settings match.
The stale-vector regression exercises a real packaging failure, including when
the corpus's data manifest has already been updated.

## Spec

**0 actionable implementation findings.** The delivery contains the corpus,
3,154 pipeline vectors, groups, scores, evidence, cases, drafts and 48 saved
queries covering all 40 public development questions without collisions.
The server forces offline mode, uses saved query replies and BM25 source search,
and does not load a model. Unknown questions have the required fallback.
Precomputed replies are checked against the loaded evidence.

The real server/browser report verifies seven stages, generation refusal, browser
editing and human review persistence across process restart. Both process audits
are empty; the browser recorded no external requests, JavaScript errors or failed
requests. The T10 matrix now links this evidence and accurately states the scope.

Per D-05, copying evidence to native Notion and the physical Wi-Fi rehearsal remain
team steps. Network isolation was verified automatically; these manual steps are
not presented as already performed. Historical G7 outputs and its private held-out
package were not changed. D-C08 honestly abstains because its synthetic sources
are absent from the editorial snapshot.

Summary: Standards 0; Spec 0. There is no unresolved implementation defect in either axis.

## Validation before publication

- Locked full suite: **1,091 passed**, 12 known missing-publication-date warnings,
  443.29 seconds; Edge browser tests included. See
  `outputs/validation/g10-final/pytest.log` and `pytest.xml`.
- Seven package boundary tests passed separately before the full suite.
- Real guarded server/browser rehearsal passed; see `report.json` and both
  zero-attempt isolation audits in the same directory.
- Wheel built and installed with `uv pip install --offline --no-deps`; its imported
  package, relocated delivery, quality/inbox and answered/abstained queries passed
  with network and model construction forbidden. See `wheel-portability.json` and
  `isolation-wheel.json`.
- Python source compilation and `git diff --check` passed.
