# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a TVN Media editor or journalist planning the day's agenda for Panama.
Their job is to decide which topics deserve investigation, check what the evidence supports, and prepare an editorial package for human approval.
They are not developers: they use the mouse, read Spanish, and expect the tools of a professional newsroom.

The digital producer is a secondary user who reuses the proposed headline and digital copy.
The banking-analyst modality of the challenge is out of scope for the UI.

The hackathon judges evaluate the product by using it without guidance from the team.
They arrive cold, so every stage of the flow must be discoverable from the interface itself.

## Product Purpose

TVN DeepMind AI turns public news and official indicators into ranked topics, evidence files and editorial drafts for human review.
It exists because a newsroom has to review scattered sources, remove duplicates, place facts in context and produce quickly, and circulation of a story is not confirmation of it.

Success means an editor can go from the ranked agenda to an approved draft, seeing at every step what is backed, what is missing and why a topic ranks where it does.
For the hackathon, success also means a judge completes all 7 stages, one useful query and one abstention case without touching the terminal (issue G6).

## Positioning

An editorial copilot that ranks and drafts, but never decides or publishes.
Every claim cites a literal source passage, the score shows its components, repetition is told apart from independent corroboration, and the product abstains when evidence is missing.

## Operating Context

- The editorial flow has 7 stages: load, organize, contextualize, prioritize, explain, produce, review (`docs/challenge/03-prototipo-flujo.md`).
- Human review states: nuevo, en revisión, requiere evidencia, aprobado como borrador, descartado. Approving a draft never publishes it.
- The demo runs offline on a frozen snapshot; the query box answers only precomputed questions without a network (D-01).
- Dates are stored in UTC and shown in Panama time (`America/Panama`).
- Judges test on their own machines, most likely laptops.

## Capabilities and Constraints

- Server-rendered FastAPI app with Jinja2, HTMX and Tailwind (ADR 0002); assets are vendored, no CDN at runtime.
- The backend routes and the 8 screens are defined in `docs/backend.md` and `docs/screen-contract.md`; the frontend must not change domain or storage code.
- UI copy is Spanish; code and engineering docs are English.
- Mouse-first: no keyboard shortcuts, command palettes, product tours or coach marks. Anything shown on hover must also be reachable by click.
- The score is an ordering tool, not a probability of truth: `P = 30R + 25I + 20U + 15N + 10E`, ranges bajo, medio, alto.
- Evidence state (insuficiente, parcial, suficiente para el borrador) is independent of the score; high priority with insufficient evidence cannot be approved.
- Headline-only content must carry the legend "basado únicamente en titular/metadatos".
- The product never labels news as true or false and never invents quotes, interviews, figures or sources.

## Brand Commitments

- The product name is "TVN DeepMind AI"; the code identifier stays `whoami`.
- TVN-inspired only: evoke TVN's editorial tone without using its logo or exact visual identity. TVN is named as the client and context.

## Evidence on Hand

- Synthetic demo set in `data/demo/` (invented news on `demo.invalid`, real World Bank, INEC and USGS figures). The UI must show a notice while `sintetico` is true.
- Real processed data in `data/processed/` and pipeline outputs in `outputs/`.
- Precomputed queries in `data/consultas_demo.jsonl` and `data/demo/consultas.jsonl`.
- No user testimonials, usage metrics or newsroom adoption exist; none may be claimed.

## Product Principles

1. Evidence before eloquence: every statement in the UI traces to a source the user can open.
2. The human decides: the product proposes, ranks and drafts; approval and publication stay with people.
3. Say what is missing: gaps, contradictions and abstentions are first-class results, not errors.
4. Obvious to a first-time user: standard, labeled controls instead of tutorials.
5. Honest about time: never present an annual historical figure as a current measurement.

## Accessibility & Inclusion

WCAG 2.2 AA contrast and visible focus; status is never conveyed by color alone.
