# Embedding validation review

Fixed point: `fa8f56a48a471c7942c022b141e70c061312cff5` (completed G10 branch snapshot). Reviewed implementation: `adb416ba293e006c834448c775589a5041d1df90`. Two independent reviewers used `git diff fa8f56a...adb416b`. This report is added after that code review, before publication.

## Standards

**0 remaining findings.** Both earlier findings are resolved: the review UI converts dates to Panama time, and cached candidate reports verify model identity, pinned hashes and installed files. The added metadata fingerprint prevents reusing rankings or grouping after news dates or outlets change.

The reviewer independently verified the committed snapshot fingerprint, matching candidate contexts and human-results identity: 30 queries, 50 pairs, 267 decisions and zero submitted human judgments. The Windows launcher checks explicit allowed emails, client integrity, readiness and anonymous access; cleanup includes the Python descendant process. Documentation accurately leaves live HTTPS authentication pending and distinguishes fixture tests from actual human judgments. No additional documented-standard breach or actionable smell was found.

Standards sources: `CLAUDE.md`, `docs/agents/domain.md`, `docs/screen-contract.md`, `docs/backend.md`, challenge/team decisions, ADR-0003, and the code-review skill's smell baseline. Live tunnel behavior remains unverified until the authorized launch.

## Spec

**0 actionable findings.** The earlier P2 is fixed: ranking/grouping identity now includes full rows; changing dates or outlets invalidates checkpoints, while vectors are reused only for identical text and model inputs.

The reviewer verified the snapshot fingerprint and equal inputs across q4, fp32 and the final package: 3,154 documents, 30 public queries, 50 ID-resolved pairs and 267 decisions. Model spaces remain separate. Human metrics remain null with zero labels and `keep_q4`, consistent with “A model change needs comparable human evidence.” App evidence confirms hybrid q4 retrieval and persistence after a real restart. Runtime measurements state their scope and limitations; the concurrent fp32 rebuild is not presented as a controlled comparison.

No reserved G7 access, fabricated human labels, automatic promotion or billing enablement was found. Human review and the protected tunnel remain pending and are disclosed; no executed private URL is claimed. Spec source: the user's approved design recorded in `docs/embedding-validation.md`.

Summary: Standards **0** remaining; Spec **0** remaining. Pending user input: real human relevance/event judgments, PC-hosting preference and allowed email for the protected tunnel.

## Follow-up: agent evaluations and optional human review

The user subsequently requested that Codex perform the evaluations and fold the manual step. Fixed point for this update: published `2c455243da9b2f802477b1b67292dfb61ccb309a`; reviewed code `74398af768b2e09ab0bf52257ec48dd05123ee81`. Human judgments are now optional for this delivery, replacing that earlier pending input; hosting preferences/email remain separate.

Standards: **0 findings**. The reviewer independently recomputed the report, confirmed exact agreement with 267 submissions/266 usable/one unknown, and checked snapshot/origin/item/grade/reviewer/rationale validation. Shared metric definitions and unknown exclusion are preserved. Agent outputs stay separate from human SQLite and human results. No documented-standard breach or actionable smell was found.

Spec: **0 actionable findings**. The reviewer verified 217 retrieval judgments, 49 scored pairs and one excluded unknown; precision numerators are q4 135/150, fp32 134/150, and hybrid/BM25 121/150. The optional human form is folded; AI results are separate and honestly attributed. q4 remains selected without changing model weights, thresholds, retrieval or Gemini. Agent development-pool metrics are not described as human ground truth or statistically significant superiority.

Validation before publication: 17 scoring/provenance/UI tests passed, two real Edge browser flows passed, wheel build passed; original human results are semantically unchanged and persisted human-label count remains zero. The later CI run verifies the published commit on Windows and Linux.
