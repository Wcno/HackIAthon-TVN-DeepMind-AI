# G5: serving the editorial workflow

The backend starts from the G2 contract (PR #32) and serves all eight screens
with the synthetic dataset. Python identifiers, modules and engineering docs
are in English; the Spanish wire fields and editorial wording follow §7.

## Run locally

```powershell
uv sync --locked --link-mode copy
uv run --locked uvicorn whoami.backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000/inbox. The app defaults to synthetic news and offline
precomputed queries. No API key is needed for this workflow. `--link-mode copy`
avoids incompatible hardlinks in a OneDrive checkout.

Environment variables are optional. To use `.env.example`, copy it to `.env`
and start with `uv run --env-file .env uvicorn ...`; the app does not load files
implicitly. Never commit `.env`.

## G6 screen contract

| Screen | View |
| --- | --- |
| Load quality | `GET /quality` |
| Ranked inbox | `GET /inbox?topic=economia` |
| News group | `GET /groups/{group_id}` |
| Official context | `GET /groups/{group_id}/context` |
| Evidence fiche | `GET /cases/{case_id}` |
| Editorial package | `GET /cases/{case_id}/draft` |
| Human review | `GET /cases/{case_id}/review`, `POST` on the same path |
| Query box | `GET /queries?q=...` |

`GET /evidence/{evidence_id}` opens the citable source fields, and `GET /health`
reports readiness, demo/offline settings and group count. Screen views return
HTML; `HX-Request: true` returns only the screen partial. The initial templates
are deliberately small so G6 can replace presentation without changing domain
or storage code. They require no CDN to serve or submit a plain HTML form.
The HTMX attributes become active when G6 vendors its JS per ADR 0002.

Review forms use English parameters: `state` (Spanish contract value), `actor`,
`note` and `expected_version` (the version rendered in the hidden field).
Stale decisions return 409; invalid transitions return 422; missing records
return 404. Errors return HTML, including a partial for HTMX requests.
G6 should configure HTMX to display error responses (409/422/503) in its target,
as HTMX does not swap error responses by default. Plain forms show the error
page directly. Opening discarded/approved content again requires a reason. Evidence
marked insufficient, or a missing draft, prevents approval. No route publishes
content. Dates in views are converted to `America/Panama`.

## Persistence and source ownership

SQLite defaults to `%LOCALAPPDATA%/whoami/editorial.sqlite3` on Windows,
outside the OneDrive checkout. Override with `WHOAMI_DATABASE` and use a
persistent local disk or volume; an ephemeral hosting filesystem will not
preserve it. This MVP has no user authentication and binds to loopback in
the documented command; a public multi-user deployment needs its own access
configuration.

At startup, validated G2 pipeline files seed the database. Restarting with the
same seed preserves human decisions and versions. New content (including its
group and cited evidence) increases the case version and revokes approval.
Removed cases are archived, excluded from active views and cannot be reviewed;
their history is retained and approval is revoked. Restoring them requires review.
Review updates use a single transaction with optimistic version checks; they
never rewrite G3/G4 JSONL outputs. The SQLite review ledger owns live state.
Human decisions are attached to a content version and ordered by UTC date.
A changed/restored case starts a new review cycle in `nuevo`; previous decisions
remain historical. Automatic invalidations are separate audit events, never
anonymous human reviews. `current_review_records(case_id)` returns the current
cycle in G2's exact record shape, compatible with `ReviewRecord` and its shared
transition validator. The interface labels decisions on older content as history.

Future dates in synthetic demo reviews are anchored before first import, with
the original synthetic timestamps preserved in their notes. Real human decision
timestamps are never shifted. Unchanged seed files do not reset decisions on restart.

Fiches and generation cache survive a process restart. Exporting SQLite
decisions back to a delivery `fichas.jsonl` is an integration concern for the
delivery lane; the source JSONL remains input data. `backend/pipeline.py` adapts
the final Pydantic contract merged by G2's developer in PR #32. Cases reference
their group for score, title, topic and evidence state; context figures are read
from evidence. Review transitions and typed state vocabulary come from G2's
shared `contracts.py`, rather than a second copy in the backend.

## G4 generation seam

`GeminiClient.generate(messages, evidence, validate=..., prompt_version=...)`
returns validated JSON. Its persistent cache key includes the full messages,
model, parameters, prompt version, evidence IDs and contents. Cache hits work
offline; misses fail honestly. Invalid outputs never enter the cache.
The `openai.AsyncOpenAI` client uses `GEMINI_BASE_URL` so the compatible endpoint
can be changed without editing code. SDK retries are disabled; this module owns
the retry budget. It retries only 429 and 503, honors `Retry-After`, caps attempts
and applies a total generation deadline. Errors omit response bodies and keys.

G4 can pass an async `query_provider(query, gemini_client, repository)` into
`create_app`. It owns retrieval, evidence gating, prompt construction and
semantic answer validation. The HTTP boundary additionally validates the G2
answer shape and literal citations. Precomputed queries always work without
the provider; a new offline query reports the D-01 fallback. With online mode
but no G4 provider, it reports unavailable generation. No live model results
are claimed by the transport tests.

Provider request shape follows the [Gemini OpenAI-compatible API](https://ai.google.dev/gemini-api/docs/openai).
SDK configuration follows the [official OpenAI Python documentation](https://developers.openai.com/api/reference/python).
Views use [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/)
and [lifespan](https://fastapi.tiangolo.com/advanced/events/).

## Verification

```powershell
uv run --locked pytest -q
```

The G5 tests exercise all eight views and fragments, cited queries and
abstention, escaped source text, restart persistence, stale decisions,
insufficient evidence, approval invalidation, 429/503 recovery, deadline,
cache invalidation and invalid provider outputs. HTTP transports are mocked;
no credentials or network are used by tests.

Publication uses `scripts/push_g5.ps1`: it checks that PR #32 was merged by
G2's developer, the final merge and latest `origin/prod` are ancestors of G5,
the checkout is clean, and tests pass. A cancelled dependency blocks push.
An open tracking issue is reported separately; the developer's integrated PR
is the evidence that its implementation is complete. Run the two-axis code
review on the final diff before invoking this script.
