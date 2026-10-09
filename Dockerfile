# The online app for a VPS behind a reverse proxy (Dokploy/Traefik): Gemini generation, hybrid
# retrieval with the pinned local EmbeddingGemma model baked in, and SQLite on the /data volume.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    WHOAMI_EMBEDDING_MODEL_DIR=/opt/whoami/model \
    WHOAMI_DEMO=0 \
    WHOAMI_OFFLINE=0 \
    WHOAMI_EMBEDDING_THREADS=2

WORKDIR /app

# Dependencies first, so code changes reuse this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev \
    && whoami download-model \
    && rm -rf /root/.cache

RUN useradd --create-home --uid 1000 whoami \
    && mkdir -p /data \
    && chown whoami /data
USER whoami
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/demo-readiness', timeout=4)"

# Refuses to start without GEMINI_API_KEY or with degraded (BM25-only) retrieval.
CMD ["whoami", "local-demo", "--host", "0.0.0.0", "--port", "8000", "--database", "/data/editorial.sqlite3"]
