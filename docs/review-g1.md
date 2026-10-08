# G1 completion review

Skill: `code-review`, with independent Standards and Spec agents.
Base requested by the user: `prod`, pinned for the final review at
`77474db4ff9b30f2ee26f4df292be6418f339fa1` after the concurrent G3/G4 merge.
Reviewed implementation: `9bfcc6df56cb7676935f572619b05350f4bfa1ce`.
Command: `git diff 77474db...9bfcc6d`.
Commits: `f01fa3d` (G1), `9b7e850` (merge current prod), `9bfcc6d` (review fixes).
Spec: GitHub issue #19, challenge sections 6–7, decisions D-01–D-04 and the GDELT handoff.

## Standards

**0 documented violations, 0 heuristic findings pending.**

The duplicated URL attribution rule is now shared in `parsing.belongs_to_outlet`
and tested with malformed URLs. DOC and GKG use the same exact-domain rule.
The manifest mirror is excluded from its own hashes and verified identical to
the root copy. Frozen raw bytes are preserved across checkout; processed JSON,
JSONL and GeoJSON use stable line endings.

The G3 compatibility change keeps unknown publication as `None` and explicit
detection metadata. The grouping loader reports omitted undated rows without
changing the G1 corpus. No conflicts with D-01–D-04 or the existing ADRs were found.

## Spec

**0 pending G1 requirements, 0 incorrect implementations, 0 scope-creep findings.**

The earlier manifest-location finding is resolved: `data/processed/manifest.json`
exists and has the same bytes as `data/manifest.json`. All processed hashes and
the exclusion of the manifest itself were verified.

The corpus keeps 3,176 news items, including 41 from GKG and 22 with unknown
publication time. Detection is never substituted for publication. The three
documented Enrique Lau articles belong to La Prensa, Telemetro and Panamá América,
satisfying the same-event, multiple-outlet acceptance criterion.

GDELT coverage remains explicitly partial: six hourly multilingual batches; DOC
captures continue to return 429. This follows the documented fallback. Updating
G3's derived embeddings after a corpus change belongs to G3; the handoff to that
lane is documented in `g1-completion.md`.

## Validation

`scripts/validate_g1.py` verifies two byte-identical offline rebuilds, 55 raw
hashes, every processed hash, identical manifest copies, GDELT timestamps and
the three same-event news IDs. Evidence: `outputs/validation/g1-runtime.json`.
The committed blobs were checked against the manifest after commit as well.
The final suite on Python 3.12 passed 635 tests, with 2 skips. The wheel and the
normal `whoami build` command also passed in the repaired workspace environment.
The existing backend retry-deadline regression retains its mocked one-hour
Retry-After, with a 0.5-second budget so SDK 3 initialization does not consume
the old 30 ms before the first request; production settings are unchanged.

Standards: 0 pending findings; Spec: 0 pending findings. No worst issue remains on either axis.
