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
