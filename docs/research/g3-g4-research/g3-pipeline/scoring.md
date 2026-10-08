# Score R, I, U, N, E (T08) and recirculation (T03)

Code: `src/whoami/pipeline/scoring.py`, `recirculation.py`, `provenance.py` on `proto/g3-pipeline`.
Every rule is deterministic and every component carries a Spanish justification that the inbox shows.

## Weights

`P = 30R + 25I + 20U + 15N + 10E`, kept as the §4 suggestion.

- Why keep them: there is no editor ranking yet to fit weights against (Precision@5 needs an independent editor pick), and the jury can check them against the challenge text.
- Why they are sensible for a newsroom: relevance to Panama and the six lines (R) and public impact (I) decide whether a story belongs in the inbox at all (55 points); urgency (U) orders what to review first; novelty (N) keeps duplicates from rising; available evidence (E) weighs least because evidence sufficiency is shown separately (`estado_evidencia`) and must not decide priority.
- Rules version: `RULES_VERSION` in `contracts.py`; bump it when a rule below changes.

## Components

| Component | Rule | Why |
|---|---|---|
| R relevance | `0.6 × has topic + 0.4 × Panama`; Panama = 1 if the text names Panama, a province, a comarca or a main institution, or the source is official or the section is `nacionales`/`economia`; 0 if every member is in `mundo` and names none; 0.5 otherwise | The topic weighs more: a Panamanian story outside the six lines is not one the newsroom covers |
| I impact | topic base (Canal and economy 0.6; public services, natural events, regulation 0.5; tourism 0.4; no topic 0.1) + 0.2 official context + 0.2 a size signal (money, %, "nacional", count of affected people or homes) | Data-backed size, never sensational words |
| U urgency | age of the newest ORIGINAL publication at the cutoff: < 24 h 1.0, < 48 h 0.8, < 72 h 0.6, < 7 d 0.4, < 14 d 0.2, else 0.1; +0.2 for an alert or a future date in the text | Old news recirculated today is not urgent (T03) |
| N novelty | max cosine of the group centroid to EARLIER groups: 0.5 → 1.0, 0.9 → 0.0, linear; all members recirculated → 0.1 | Group size never enters: repetition is not novelty (T02) |
| E evidence | `0.4 × min(provenances, 3)/3 + 0.3 × primary source + 0.3 × text beyond the headline` | Independent origins, not outlets; a fourth copy adds nothing |

Evidence state (independent of the score): `suficiente_para_borrador` with an official source that has a description, or 2+ provenances and some description; `parcial` with any description, official context or 2+ provenances; `insuficiente` otherwise.
A high score with insufficient evidence cannot be approved (enforced by `verify`).

## Recirculation (T03)

- Rule A (metadata): an item dated by feed or page whose `fecha_modificacion` is more than 7 days after `fecha_publicacion` gets `recirculada_en`.
- Rule B (inside a group): a near-identical copy by the same outlet more than 3 days after an earlier member takes the earlier date and is marked recirculated.
- On real data neither rule fires: G1 drops recirculated old articles by their original date (largest modification gap in the corpus: 1 day). Open decision for G1, see the README.
