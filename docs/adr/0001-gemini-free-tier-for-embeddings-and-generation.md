---
status: accepted
date: 2026-10-06
---

# Gemini API free tier for embeddings and generation

We use the Gemini API free tier for both embeddings and strict-JSON generation.
It is reached through the OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) with the Python `openai` client, so `base_url` stays swappable.
We chose a single cloud provider and no local models to keep the stack simple during the 48h event; the accepted risk is that Google does not publish free-tier limits.

## Models

- Generation: `gemini-3.5-flash-lite` only.
  `gemini-3.8-flash` was rejected after the smoke test (`scripts/smoke_gemini.py`, 2026-10-06): it returned 503 "high demand" once and took 268 s on the retry, against about 2 s for flash-lite.
- Embeddings: `gemini-embedding-2`, at a fixed dimension (768).

## Considered options

- **Local (QVAC/Qwen and `multilingual-e5`)**: rejected because the team prefers not to run local models, and the app is deployed on free hosting.
  Free tiers offer about 512 MB of RAM or serverless size limits, which `sentence-transformers` with PyTorch does not fit.
  An ONNX build (`fastembed` with quantized `multilingual-e5-small`) would fit a small VPS but still not serverless.
  This also rules out the local MiniLM + FAISS plan in `prod`'s `docs/PLAN.md`.
  Supersedes the `NoSkill` branch plan (D-02); D-05 (no `tools`, strict JSON) still holds.
- **Groq**: strict JSON only on `gpt-oss-20b/120b` and `qwen3.8-27b`, no embeddings, 8K TPM; kept as a generation fallback by changing only `base_url`.
- **OpenRouter `:free`**: 50 requests/day without credits, not enough for the benchmark.
- **Cloudflare Workers AI**: viable (`bge-m3`, 10K neurons/day), but adds another platform with no clear gain.

## Consequences

- Limits (RPM/RPD/TPM) are per project and only visible in the AI Studio dashboard; check them when creating the key.
- Headline embeddings are computed once and stored in numpy; only the query is embedded at runtime.
- Answers are cached by a hash of prompt, model and evidence IDs, so the benchmark and demo can be rerun without spending quota.
- 429 responses are handled with exponential backoff retries.
- The embedding model is pinned: `gemini-embedding-001` and `gemini-embedding-2` spaces are not comparable, and switching means recomputing everything.
- `gemini-embedding-2` sets the task in the prompt text, not via a parameter; queries and documents must use consistent prefixes.
- On the free tier Google may use the data to improve its products; acceptable because inputs are public news, and documented as a limitation.
- Panama is a supported region.

## Sources (checked 2026-10-06)

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/embeddings
- https://ai.google.dev/gemini-api/docs/openai
- https://ai.google.dev/gemini-api/docs/available-regions
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/structured-outputs
- https://openrouter.ai/docs/api-reference/limits
- https://developers.cloudflare.com/workers-ai/platform/pricing/

## Note, 2026-10-07: embedding quota, experiment model and rate limits

- **Embeddings no longer go to Gemini.** The free tier counts `gemini-embedding-2` per text: about 100 texts per minute and 1,000 per day, measured. The 2,941-item corpus alone needs three days of quota.
  A local model reaches the same retrieval quality on 30 labeled queries (nDCG@10 0.87 local, 0.89 Gemini), so ADR-0003 (proposed) moves embeddings to `embeddinggemma-300m` and supersedes the embedding part of this ADR.
- **Proposal: `gemma-4-26b-a4b-it` for experiments and offline batch work, `gemini-3.5-flash-lite` for production answers.**
  Gemma's free tier is 30 RPM, 16K TPM and 14,400 RPD, against 15 RPM and 500 RPD for the flash-lite models, so tuning prompts, labeling and classifying the whole corpus fit in a day only on Gemma.
  Its 16K tokens per minute is the real throughput limit: prompts must stay short.
- **Gemma needs a JSON schema.** With `response_format` json_schema it answers in about 1 s; without one it writes a `<thought>` block and took 33 s. It sometimes degenerates into whitespace inside JSON (one call hung 600 s), so every call sets `max_tokens`, a 90 s timeout, and invalid JSON is never cached.
- **Rate limits are per project and per calendar minute, shared by every process.** A sliding-window limiter at 100 % still peaked at 32/30 RPM and 14.7K/16K TPM on the dashboard. The shared layer now targets 80 % of RPM and 70 % of TPM, and a new process resumes the window from the ledger.
- **Not used:** `gemma-4-31b-it` (46 s per call) and `gemini-3.8-flash` (20 RPD).
