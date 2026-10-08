# G8 completion review

Fixed base: `origin/prod` at `16bf92c`.
Reviewed implementation: `f3e708d` (`git diff 16bf92c...f3e708d`).
Issue: [#26 · G8 Notion, pitch y despliegue](https://github.com/Wcno/hackiaton-whoamisfc/issues/26).

The `code-review` skill ran independent Standards and Spec reviews in parallel. Two rounds
were run. Round 1 findings were corrected in `4d5d0ef`; round 2 findings in `f3e708d`. A final
grep confirmed that the corrected statements no longer appear in the pages.

Tests: `uv run --locked pytest -q` on `16bf92c` plus G8 changes: 637 passed, 0 failed
(`outputs/validation/g8-pytest.log`, `outputs/validation/g8-junit.xml`).

## Standards

**0 hard violations open.** The pages follow the Notion structure of §5 of the challenge
(`docs/challenge/05-notion.md`), one page per required section.

Judgement calls, left as they are:

- "Caso" has three meanings: CU-xx (use case), CASO-… (ficha) and G-… (group). The glossary in
  `docs/notion/05-casos-y-evidencias.md` defines them.
- Some figures repeat across pages (token count and query count). Each has a single source
  cited on the page where it appears.
- `docs/notion/02-plan-y-decisiones.md` holds backlog, decisions, findings and pending items under
  separate headings. It mirrors the single «Plan y decisiones» page that §5 requires.

## Spec

Covered in the repository:

- The eight Notion pages of §5, mirrored in `docs/notion/`.
- Design: model, provider, prompts (with file paths), parameters, measured usage and limits.
- Risks and ethics: rights per source, privacy, injection controls, out-of-scope items.
- T01-T10 matrix: input, expected result, observed result, the tests that cover each, and correction.
- Decisions (DP-01 to DP-04) and a backlog of twelve tasks with their evidence.

Pending, and marked as pending in the pages (not claimed as done):

- **Notion Business space.** It is outside GitHub and depends on the license (§5 admission rule).
- **Free-tier deployment.** Issue #26 leaves it for the end. It depends on G6, which is not in `prod`.
- **Pitch and demo script, and rehearsal with Wi-Fi off (T10).** The issue assigns them to the team.
- **Ficha with insufficient evidence.** §5 requires one. The generator skips insufficient groups on purpose.
  Group `G-61c55dfdbb` is documented as the case, but it has no ficha.
- **Responsible persons and reviewer.** All fichas are `nuevo` with no reviewer assigned.
- **Snapshot-level hash.** The manifest has a SHA-256 per file. §5 asks for a snapshot hash.
- **Corpus reconciliation.** `noticias.csv` lists 3,176 news items; `evidencias.jsonl` lists 2,941.
  The 235 difference is not documented in the repository.
- **Embeddings status.** ADR-0003 (local embeddings) is `proposed`. The team note in
  `docs/challenge/00-decisiones-del-equipo.md` says «No se usan modelos locales». The team must
  decide which applies.
- **Human validity review.** 0 of the 30 claims required by §9.1 have been reviewed by people.
