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
return 404. API errors currently carry a JSON `detail` for the frontend to
display. Opening discarded/approved content again requires a reason. Evidence
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
Review updates use a single transaction with optimistic version checks; they
never rewrite G3/G4 JSONL outputs. The SQLite review ledger owns live state.
Seed history is ordered by UTC date. Subsequent case versions supersede seed
records even when synthetic demo timestamps are in the future. The real
decision timestamp is preserved.

Fiches and generation cache survive a process restart. Exporting SQLite
decisions back to a delivery `fichas.jsonl` is an integration concern for the
delivery lane; the source JSONL remains input data. G2 still has requested
schema changes; `backend/pipeline.py` is the only file that adapts its loader
and serialization names. Reconcile it with the developer's final contract
before pushing G5.

## G4 generation seam

`GeminiClient.generate(messages, evidence, validate=..., prompt_version=...)`
returns validated JSON. Its persistent cache key includes the full messages,
model, parameters, prompt version, evidence IDs and contents. Cache hits work
offline; misses fail honestly. Invalid outputs never enter the cache.
The HTTP client retries only 429 and 503, honors `Retry-After`, caps attempts
and applies a total generation deadline. Errors omit response bodies and keys.

G4 can pass an async `query_provider(query, gemini_client, repository)` into
`create_app`. It owns retrieval, evidence gating, prompt construction and
semantic answer validation. The HTTP boundary additionally validates the G2
answer shape and literal citations. Precomputed queries always work without
the provider; a new offline query reports the D-01 fallback. With online mode
but no G4 provider, it reports unavailable generation. No live model results
are claimed by the transport tests.

Provider request shape follows the [Gemini OpenAI-compatible API](https://ai.google.dev/gemini-api/docs/openai).
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
