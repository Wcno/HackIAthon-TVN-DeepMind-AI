# Deployment: Oracle VPS with Dokploy

The `Dockerfile` builds the online application: Gemini generation, hybrid retrieval
with the pinned EmbeddingGemma q4 model (downloaded during the build, about 210 MB)
and the human edits/reviews in SQLite. It runs `whoami local-demo`, which refuses
to start without a Gemini key or with BM25-only retrieval, so a broken deploy fails
its health check instead of serving a degraded app.

The lockfile has Linux wheels for x86_64 and aarch64, so the image builds on both
Oracle shapes (AMD and Ampere). A 512 MB memory limit is too small for the local
model ([spike](research/local-embeddings-spike.md)).

## Dokploy application

1. **Source:** this GitHub repository, branch `prod`, build type **Dockerfile**
   (path `Dockerfile`, context `.`).
2. **Environment:** `GEMINI_API_KEY=<key>`. Optional:
   `WHOAMI_GENERATION_DAILY_LIMIT` (provider requests per day; the app spends at
   most 40 % of it, 200 by default) and `WHOAMI_EMBEDDING_THREADS` (2 by default).
3. **Volume:** mount a named volume at `/data`. It holds `editorial.sqlite3`;
   without it every redeploy loses drafts and reviews.
4. **Domain:** container port `8000`, HTTPS with Let's Encrypt.

The first start takes a few seconds to load the model. Dokploy can check
`/demo-readiness`, which reports `"ready": true` and the retrieval mode without
exposing the key or paths.

## Access

The app has no login. Anyone with the link can edit drafts, record reviews and
spend the daily Gemini quota; the daily cap bounds the spending. To restrict it,
add Basic Auth to the application in Dokploy.
