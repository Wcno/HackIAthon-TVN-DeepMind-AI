# G10 QVAC work in progress — handoff

Development stopped at the user's explicit request on 2026-10-08. **Do not merge this checkpoint, close G10, or describe it as complete.** Continue on `feat/g10-qvac`; review and validate before publishing subsequent changes.

Pre-push checkpoint findings: [Standards and Spec review](review-g10-qvac-checkpoint.md).

## Branch and inherited work

This separate worktree was created from `origin/prod` at `11538206dc699699f54c11b5f33b86efa59b9cc1`, then fast-forwarded through G10 PR #46 and model-validation PR #47. The QVAC-only review baseline is `06cb2166720d58a25fc7c783a0d3ad126187acfc`.

PR #47's reproduced online-query HTTP 503 came from the launcher's artificial daily cap (20 requests became an eight-call shared budget). Commit `06cb216` removes that override while preserving configured limits, reservations and the quota ledger. The same new Canal question returned HTTP 200 with evidence after restart; its 14 regression/quota tests passed. GitHub Linux and Windows checks for that commit both passed. This repair does not prove local generation works.

Worktree on this PC: `C:\Users\canow\OneDrive\Escritorio\AI\TVN\hackiaton-qvac`. Preserve unrelated changes in the main checkout, especially `.env` and the local deletion of `.env.example`. Do not interrupt other agents' worktrees. Existing online demo ports 8765 and 8766 belong to earlier work.

## Implemented checkpoint

- `WHOAMI_GENERATION_PROVIDER=qvac` selects a loopback-only JSON generator, without a cloud key or cloud quota ledger. `WHOAMI_OFFLINE=1` is required; no alternative provider is tried.
- `WHOAMI_QVAC_BASE_URL` defaults to `http://127.0.0.1:11435/v1/`; literal loopback addresses only, no redirects or environment proxies. `WHOAMI_QVAC_MODEL` defaults to `g10-generator`.
- Local replies are checked by the existing evidence/schema validators and cached separately. Thinking is disabled (`reasoning_budget:false`); incomplete generations are rejected.
- Queries, case generation and Co-News can use local generation while retaining the existing ONNX EmbeddingGemma q4 retrieval. UI controls distinguish cached-only offline from local generation. Co-News suggestions remain opt-in and label their QVAC origin.
- `src/whoami/qvac_runtime/package.json` and lockfile pin CLI 0.15.0 and SDK 0.21.0. **There is no installer, launcher, packaged worker or `qvac-demo` command yet.**

## Validation completed

- First public query test failed before implementation because Settings did not accept `generation_provider`; query tests then passed (12 tests including existing live queries).
- First local case-flow test failed because the offline button was disabled; after the UI change, 15 local/live-case tests passed, including case persistence across restart.
- Latest `python -m pytest tests/test_qvac.py tests/test_editor.py -q`: **20 passed**. This uses injected HTTP replies, not real-model evidence quality.
- Real CLI/model probe loaded the pinned GGUF and answered a fresh strict-JSON request through `/v1/chat/completions`: HTTP 200, approximately 6.53 seconds, `finish_reason=stop`. The runtime log reports **backend=cpu, about 3.6 tokens/second**, despite the requested GPU config. GPU placement still needs diagnosis. That was a minimal greeting, not an editorial acceptance test.
- A real-corpus query through the application was started but has no confirmed successful result at handoff. Do not count it as passed.
- Full suite, wheel, browser flow, Linux QVAC runtime, cold network isolation, physical Wi-Fi-off rehearsal and Notion evidence are **not completed** for this checkpoint.

## Runtime findings and reproduction

Read [the primary-source research](research/qvac-offline-runtime.md) first. Local installed packages are in `.cache/qvac/node_modules` (ignored, not included in Git). Node 24.19.0, Windows x64, RTX 5060 Laptop 8 GiB, driver 616.92. Vulkan loader reports 1.4.341 even though `qvac doctor` warns that it could not find the ICD.

The default SDK worker imports every plugin. Its first startup failed before IPC with a Windows Application Control block on the unused `@qvac/fabric-win32-x64` addon. **Do not disable the protection.** A custom worker loading only the required completion plugin established IPC and loaded the LLM. The supported `QVAC_WORKER_PATH` override was used. Tested prototype `.cache/qvac/worker-probe.mjs` has diagnostic logs; replace those with a reviewed packaged worker. Its essential assembly is:

```javascript
const { initializeWorker, ensureRPCSetup } = await import('@qvac/sdk/worker-lifecycle');
const { registerPlugins } = await import('@qvac/inference/plugins');
const { llmPlugin } = await import('@qvac/inference/llamacpp-completion/plugin');
const { hasRPCConfig } = initializeWorker();
registerPlugins([llmPlugin]);
if (hasRPCConfig) ensureRPCSetup();
```

Verified model already on this PC:

- `C:\Users\canow\.cache\whoami\qvac\models\Qwen3.5-4B-Q4_K_M.gguf`
- Publisher: `unsloth/Qwen3.5-4B-GGUF`, revision `e87f176479d0855a907a41277aca2f8ee7a09523`.
- Size: 2,740,937,888 bytes; SHA-256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` (locally verified).

Prototype `.cache/qvac/probe.config.json` configures alias **`qwen-local`**, not the app's default alias. Its model is an absolute local `src`, `type:"llm"`, `default:true`, `preload:true`, config `ctx_size:16384`, `gpu_layers:99`, `"main-gpu":"dedicated"`. Prototype command:

```powershell
$env:QVAC_WORKER_PATH=(Resolve-Path .cache/qvac/worker-probe.mjs).Path
node .cache/qvac/node_modules/@qvac/cli/dist/index.js serve --config .cache/qvac/probe.config.json --openai --no-default --host 127.0.0.1 --port 11435 --no-lazy-load
```

The standalone model probe is `.cache/probe_generation.py`; application probe is `.cache/probe_qvac_app.py`, using a separate `.cache/qvac-probe.sqlite3`. These are local diagnostic artifacts, not portable delivery or committed acceptance evidence. Models, node_modules and credentials are intentionally not committed. The temporary QVAC engine and application probe are stopped when handing off.

## Required next steps

1. Read the checkpoint review findings. Resolve them in a subsequent commit; do not treat a review of a partial checkpoint as approval to merge.
2. Package the minimal worker and add explicit preparation/verification/serve commands. Preparation may download pinned artifacts; serving must verify them and fail without downloading or silently switching providers. Check model identity rather than assuming any process at the configured alias serves this GGUF.
3. Keep ONNX corpus/query embeddings consistent. If switching to QVAC GGUF embeddings, rebuild all 3,154 vectors into a separate manifest; never reuse ONNX vectors for GGUF queries.
4. Update D-01/ADR-0001 with the user's new local-model requirement, preserving the frozen fallback. Existing G10 #28 still says no local models; the user's explicit QVAC instruction supersedes that scope, but the docs have not yet been updated.
5. Validate fresh supported and unsupported questions, fresh case/draft generation, Co-News edits, citations, grounding, malformed/truncated output, missing model, deadlines/cancellation and persistence/review after restart. Never present provider failure as a factual abstention.
6. Audit actual Node/Bare/native processes as well as Python and browser under denied non-loopback network access, including cold startup. Do not claim that loopback URLs alone establish offline operation. Do not disable the user's Wi-Fi without coordinating a physical rehearsal.
7. Run the full suite, wheel/build and browser checks on Windows/Linux; apply Standards and Spec code review; publish final evidence and the T01–T10/Notion matrix honestly. Only then consider integration into prod and issue closure.

The user requested a checkpoint for another agent, not an automatic restart, merge or deployment.
