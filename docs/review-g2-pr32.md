# PR #32: G2 review before building G5

Reviewed at `ded96a832327d550ba4ec5e4884efc708e767623` against fixed base
`c2a9067ff0e7fe14a45f691f25dcb6f798ad279d`. The Standards and Spec axes ran
independently using the `code-review` skill. No GitHub review or approval was
submitted. Existing requested changes belong to G2's developer.

Update: NoSkill007 implemented the four requested changes in `92c3e6e` and
merged PR #32 into `prod` at `bcc0fba` on 2026-10-07. G5 uses that final
Pydantic/English contract. Findings below describe the originally reviewed
revision, not the updated state. The short demo-script duration remains a
separate demo-content limitation; G5 serves those supplied drafts unchanged.

## Standards

- **P1:** Review state is duplicated in `Group`, `Case` and the review ledger.
  `store.py:130–149` requires these copies to agree and takes the last line,
  rather than the latest UTC date. This blocks independent G5 updates. It also
  creates possible Shotgun Surgery. The existing PR review requests one owner.
- **P1:** `store.py:26–46` reconstructs primitive values without checking their
  types; `schemas.py:34,164` accepts impossible dates. This violates the
  requested Pydantic migration and can crash callers outside validation.
- **P2:** Fiches/context duplicate group/evidence facts without validating all
  copies (`schemas.py:219–241,292–306`, `store.py:130–137`). The existing review
  requests references or checks to prevent inconsistent screen values.
- **P2:** Spanish engineering names and `docs/contrato-pantallas.md` conflict
  with the user's English code requirement and the existing PR review's naming
  convention. Spanish challenge fields and user-facing wording remain valid.

Four integration-condition findings. The most severe within Standards is the
duplicated review ownership that prevents independent lane writes.

## Spec

- **P1:** The challenge requires recording acceptance, corrections and discard
  (`docs/challenge/03-prototipo-flujo.md:23`), but adding a valid human review
  rejects the whole package until G3/G4 outputs are rewritten (`store.py:135,147`).
  Current state also depends on line order instead of review date.
- **P2:** ISO 8601 UTC dates are required by §7, yet evidence with
  `2026-13-45T99:00:00Z` can be constructed (`schemas.py:34,164–166`).
- **P2:** The challenge asks for a 45–60 second script
  (`docs/challenge/03-prototipo-flujo.md:32`). Demo scripts in
  `demo.py:183,226,275,309` are only one or two sentences and have no documented
  timing criterion. A complete editorial demo needs the stated format.

Three Spec findings. The most severe within Spec is persistence of independent
human decisions. The eight screens, §7 fields and synthetic fixtures are present;
team agreement is still pending while the PR has requested changes.
