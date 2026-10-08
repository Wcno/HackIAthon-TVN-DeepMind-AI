# Embedding validation and a private PC demo

Approved design, 2026-10-08: preserve EmbeddingGemma ONNX q4 for retrieval/grouping and preserve Gemini generation. Compare q4, fp32 and BM25 using named human reviewers on public development queries and event pairs. Spanish relevance takes precedence over preparation speed. No payment card, subscription or enabled billing account may be introduced. A model change needs comparable human evidence; this experiment never promotes a candidate automatically.

Updated user instruction, 2026-10-08: Codex performs the evaluations and waives the pending manual step. The [completed agent assessment](research/agent-embedding-evaluation.md) submits all 267 decisions, explicitly as AI judgments. Human review remains optional and separately attributed; it is not a delivery gate. q4 remains the practical recommendation, and no automatic production change occurs.

## Frozen comparison

Run from the repository checkout with its installed Python environment:

```powershell
whoami compare-embeddings prepare --directory outputs/experiments/embedding-validation --threads 4
whoami compare-embeddings review --directory outputs/experiments/embedding-validation --port 8766
whoami compare-embeddings score --directory outputs/experiments/embedding-validation
whoami compare-embeddings score-agent --directory outputs/experiments/embedding-validation
```

Preparation runs on CPU in separate processes using pinned ONNX files and the exact production text prefixes/tokenizer. The existing q4 corpus must match its model hashes, ordered IDs, vector hash and full text fingerprint. fp32 embeds every document in its own space, casts to the same float16 storage, and verifies its files against the publisher hashes of revision `5090578d9565bb06545b4552f76e6bc2c93e4a66`. No document/query vectors cross model spaces. q4's corpus is reused; its rebuild time is deliberately null, so this run cannot compare full rebuild speed. The complete process memory measurement includes event grouping, not just embedding weights or the full web app. Warm query/search latency includes index creation and excludes lexical fusion and startup; it is not an HTTP latency claim.

fp32 files must already exist at `~/.cache/whoami/models/local/embeddinggemma-300m-fp32/{onnx/model.onnx,onnx/model.onnx_data,tokenizer.json}`. They are public downloads from the pinned [ONNX publisher](https://huggingface.co/onnx-community/embeddinggemma-300m-ONNX/tree/5090578d9565bb06545b4552f76e6bc2c93e4a66), with no paid API calls. `prepare` itself performs no downloads. Candidate checkpoints can be resumed only against identical inputs, including full news metadata and current model-file hashes. Vector-only caches separately bind the exact embedding inputs and model hashes; changing an outlet/date invalidates rankings and groups even when the document vectors remain reusable. Use a new directory after a snapshot has been frozen.

The review pool uses all 30 public G3 queries and a reproducible 50-pair sample from public historical candidates, resolved by news IDs rather than obsolete positional indices. Historical machine labels are discarded. It never accesses G7's 20 reserved queries. Retrieval compares five candidates: q4, fp32, BM25, and each embedding plus the existing BM25/RRF recipe and cosine gate. The corpus is the same dated-news subset for all candidates; official indicators and the complete assistant workflow are outside this experiment. Event grouping uses the current average linkage/72-hour window/0.275 threshold, without LLM overrides. BM25 has no event-grouping score, since it is a retrieval baseline.

The local review page at `http://127.0.0.1:8766` hides model names, rankings and machine labels. A human chooses relevance 0/1/2 or same event/ongoing story/different event; uncertainty remains unknown. SQLite keeps the reviewer, timestamp, current label and history across restarts, bound to the frozen snapshot fingerprint. Revisions are available through the page's decision list. It is a local evaluation UI, not a publicly authenticated service.

When a validated `agent-judgments.jsonl` exists, the page displays agent progress, folds the optional human form, and offers a separate model-results page at `/agent-results`. That results page reveals model names; people seeking a future blind human evaluation should avoid it. Agent judgments use JSONL and `score-agent`, not the human SQLite store. Their scores carry explicit agent origin and never claim `human_review_complete`. Submitted unknowns count as assessed items, while remaining excluded from metrics with explicit coverage.

Only fully human-judged query pools contribute to retrieval averages; unknowns never become irrelevant labels. Precision@5 divides by five, including missing hits. Pooled recall divides by all relevant documents in the union pool, including relevant results outside a candidate's top five. Pooled nDCG uses the ideal ranking within that judged pool. Each metric records its contributing query count; no-relevant-result pools have undefined recall/nDCG. These are development-pool metrics, not full-corpus recall or a reserved-set evaluation. Pair F1 records TP/FP/FN/TN, coverage, and is undefined when there are no positives or positive predictions. The candidate pair pool was historically selected using models; its sample is not an unbiased all-event estimate. Results stay `awaiting_human_review` until every item has a usable human judgment, and the decision remains `keep_q4` even after all judgments are complete.

## Canonical app on the PC

```powershell
$env:WHOAMI_ENV_FILE = 'C:\path\to\existing\.env'
$env:WHOAMI_OFFLINE = '0'
$env:WHOAMI_DEMO = '0'
$env:WHOAMI_EMBEDDING_THREADS = '4'
whoami local-demo --database "$env:LOCALAPPDATA\whoami\private-demo\editorial.sqlite3" --port 8765
```

This serves the canonical application, with q4 semantic retrieval, generation through the existing Gemini configuration, and a separate persistent database. No key is copied or printed, no billing is enabled and no generation provider/model is changed. Startup refuses BM25 degradation. `/demo-readiness` confirms the actual retrieval mode. Provider requests are capped at the smaller of the existing limit and 20 daily calls; this is a quota guard, not evidence of the account's billing status or provider uptime. This launch does not change G10: `offline-demo serve` still uses no inference and only frozen answers.

## Temporary private HTTPS access

PowerShell 7.2+:

```powershell
./scripts/start_private_demo.ps1 -AllowedMail 'reviewer@example.com' -EnvFile 'C:\path\to\existing\.env' -Port 8765
```

The launcher downloads the pinned official Windows client `cloudflared 2026.10.0`, verifies its SHA-256, checks `--allowed-mail` support, then starts the app and protected Quick Tunnel in hidden windows. It refuses a occupied port or missing configuration and publishes the URL only after anonymous HTTP access is blocked by an email/PIN gate. Failures stop only processes created by that launch. Local logs/session IDs live in ignored `.cache/private-demo/`; the database stays in `%LOCALAPPDATA%`. The final launch output includes the exact process IDs to stop. Stopping those processes preserves SQLite.

This route requires no Cloudflare account/domain/payment method. The URL changes on each launch, dies when the tunnel stops and requires this PC and its connection to remain active. It has no availability guarantee and does not support SSE. It is a temporary private demonstration, not independent production cloud hosting. See [official Quick Tunnel behavior](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) and the [provider feasibility research](research/no-billing-hosting.md). Access requires the approved individual reviewer email; no unrestricted tunnel is started while that information is missing. No account creation or paid-host provisioning is part of these scripts.

## Executed evidence

The [frozen snapshot](../outputs/experiments/embedding-validation/snapshot.json) contains 30 public queries, 50 ID-resolved event pairs, five retrieval candidates, and **267 review items**. [Human results](../outputs/experiments/embedding-validation/human-results.json) still contain zero judgments and null quality metrics. [Agent results](../outputs/experiments/embedding-validation/agent-results.json) now cover all 267 assessed items, with one unknown event pair and no human-validated winner claimed. The practical recommendation is to retain q4; the complete rationale and candidate scores are in the [agent assessment](research/agent-embedding-evaluation.md).

The final sequential query runs used four CPU threads on this PC, with the existing app idle. q4 measured 238 ms median query plus search/index construction and 673 MiB peak run RSS; fp32 measured 189 ms and 986 MiB. These are observed development-run timings, not guaranteed HTTP latency or hosting memory requirements. See [q4 provenance](../outputs/experiments/embedding-validation/q4.json) and [fp32 provenance](../outputs/experiments/embedding-validation/fp32.json). Both repeated query runs reused validated corpus vectors. The original full fp32 build took 753 seconds while other validation was running; the saved rebuild time is observational and is not a controlled q4/fp32 rebuild comparison. Both models were downloaded and hash-verified, and no paid model API was called by preparation.

The [real local-app check](../outputs/validation/embedding-validation/local-demo.json) confirms hybrid q4 startup, seven screens, a draft surviving a real process restart and restoration of the test title. No human review decision was submitted by the agent. The protected tunnel has **not** been started: the allowed email and user's PC-hosting preference remain pending. Client version/hash and flag availability were checked locally; they do not prove a live authenticated tunnel. The real-browser review test uses a tiny temporary fixture database, never these actual human-label files.

## Delivery boundary

Branch `feat/embedding-validation` starts at G10 commit `fa8f56a`, so its pull request is stacked on `feat/g10-offline` (PR #46) while G10 is unmerged. The development snapshot and performance report are reproducible artifacts. Human labels remain local until the responsible human elects to share/export them; test fixture labels are never written to the actual comparison. The current production model remains q4.
