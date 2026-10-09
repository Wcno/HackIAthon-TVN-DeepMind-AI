# QVAC local runtime for G10

Date: 2026-10-08. Research only: no inference, model download, installation, network isolation or GPU validation was performed for this note. The user's new requirement permits fresh local generation and supersedes G10's earlier no-local-model decision; implementation must update that decision explicitly.

## Versions and Windows requirements

The npm registry identifies `@qvac/cli@0.15.0` with git commit `c5ea23c997e1421e34aae436508e73af7d9e0972` and an SDK dependency `^0.21.0`. SDK `0.21.0` identifies commit `ffff93cc7c31ea12c547c4b6bbfce4168f6a8e2c`. Pin both exact packages plus the lockfile; pinning CLI alone does not fix a caret transitive dependency. [CLI package metadata](https://registry.npmjs.org/@qvac%2fcli/0.15.0), [SDK package metadata](https://registry.npmjs.org/@qvac%2fsdk/0.21.0).

QVAC documents Windows 10+ x64 and **Vulkan >=1.4, including CPU-only inference**. `qvac doctor --json` checks the host. Minimum RAM is 2 GB; 5 GB free disk is recommended. The known PC has an i7-13650HX, about 31.7 GiB RAM and RTX 5060 Laptop with 8 GiB VRAM. This makes a 4B Q4 model plausible, but available VRAM, driver support and actual inference remain untested. [Official system requirements](https://docs.qvac.tether.io/sdk/system-requirements/).

## HTTP and local file configuration

`qvac serve --openai --host 127.0.0.1 --port 11434` exposes `/v1/chat/completions` and `/v1/embeddings`. Model aliases must be configured and included in every request; `default:true` does not supply an omitted model name. Set context explicitly because the documented default is only 1,024 tokens including input/output. [HTTP server](https://docs.qvac.tether.io/cli/http-server/).

Use absolute filesystem `src` values, `type:"llm"` / `type:"embeddings"`, `preload:true`, an absolute `cacheDirectory`, and `serve.load.lazy:false`. Do not use registry constants or HTTPS sources in the offline serving config. [Configuration](https://docs.qvac.tether.io/sdk/configuration/).

Published source config names are different for the two engines:

| Role | Relevant config fields |
| --- | --- |
| Generation | `ctx_size`, `device`, `gpu_layers`, `"main-gpu"`, `predict`, `"flash-attn"` |
| Embeddings | `device`, `gpuLayers`, `mainGpu`, `batchSize`, `embdNormalize`, `flashAttention` |

For generation `"main-gpu":"dedicated"` selects the dedicated class. Leaving `gpu_layers` unset allows automatic placement fitting; an explicit value disables that fitting. For embeddings `mainGpu:"dedicated"` and `embdNormalize:2` select dedicated GPU and Euclidean normalization. Do not invent `nGPUlayers` or `main_gpu` keys at this SDK boundary. [Published model schemas](https://github.com/tetherto/qvac/blob/ffff93cc7c31ea12c547c4b6bbfce4168f6a8e2c/packages/inference/src/schemas/llamacpp-config.ts).

Start with bounded context (for example 8,192) and bounded output (for example 1,024 tokens), then measure actual prompt size, memory and response quality. Those values are implementation proposals, not verified optimal settings. Prefer one generation request at a time and at most one repair attempt; never retry indefinitely after invalid output or model absence.

## Structured output contract

The HTTP shape is `response_format`, not Gemini's `response_schema`:

```json
{
  "model": "g10-generator",
  "messages": [{"role": "user", "content": "Return the requested Spanish case object."}],
  "max_tokens": 1024,
  "reasoning_budget": false,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "g10_case",
      "strict": true,
      "schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"]
      }
    }
  }
}
```

**Published CLI source requires a nonempty `json_schema.name`**, despite the prose docs calling it optional. It forwards `strict`; boolean `reasoning_budget:false` becomes numeric zero. Positive reasoning caps are not accepted by this HTTP adapter even though the lower-level SDK schema supports them. Structured JSON and tools cannot be combined. Validate JSON, schema, citation identifiers and editorial evidence in Python regardless of sampler constraints; reject `finish_reason:"length"` rather than accepting truncated content. [Published HTTP mapping](https://github.com/tetherto/qvac/blob/c5ea23c997e1421e34aae436508e73af7d9e0972/packages/cli/src/serve/extensions/openai/schemas/common.ts), [chat route](https://github.com/tetherto/qvac/blob/c5ea23c997e1421e34aae436508e73af7d9e0972/packages/cli/src/serve/extensions/openai/routes/chat.ts).

## Reproducible candidate artifacts

These immutable revisions and LFS SHA-256 values were read from the publishers' Hugging Face API metadata on this date. They are expected hashes, not locally downloaded-file verification.

| Artifact | Pin |
| --- | --- |
| Generator | Repository `unsloth/Qwen3.5-4B-GGUF`; revision `e87f176479d0855a907a41277aca2f8ee7a09523`; file `Qwen3.5-4B-Q4_K_M.gguf`; size 2,740,937,888 bytes; SHA-256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |
| Q4 embedder | Repository `admiralakber/embeddinggemma-300m-Q4_K_M-GGUF`; revision `090f6e5306aa15900bcc82a585c404df7f48bf46`; file `embeddinggemma-300m-q4_k_m.gguf`; size 236,337,120 bytes; SHA-256 `2decb24229f3876b66edee3f0c825edcf3ac46206819ec51aff29fd97e8ce529` |
| Alternative embedder from llama.cpp organization | Repository `ggml-org/embeddinggemma-300M-GGUF`; revision `0f741b5a6585bd53aeb15cd1372c56f2a0f65e12`; file `embeddinggemma-300M-Q8_0.gguf`; size 333,590,944 bytes; SHA-256 `b5ce9d77a3fc4b3b39ccb5643c36777911cc4eb46a66962eadfa3f5f60490d63` |

[Qwen immutable file](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/blob/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf), [Q4 embedding immutable file](https://huggingface.co/admiralakber/embeddinggemma-300m-Q4_K_M-GGUF/blob/090f6e5306aa15900bcc82a585c404df7f48bf46/embeddinggemma-300m-q4_k_m.gguf), [Q8 embedding immutable file](https://huggingface.co/ggml-org/embeddinggemma-300M-GGUF/blob/0f741b5a6585bd53aeb15cd1372c56f2a0f65e12/embeddinggemma-300M-Q8_0.gguf).

Qwen's base model is Apache-2.0 and multilingual; its published benchmark/card is not evidence of Spanish editorial reliability in this app. The Unsloth export is a separate publisher artifact, not a Qwen-authored GGUF. Use text only; a vision projector is unnecessary here. [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-4B), [export publisher](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF).

EmbeddingGemma remains under Gemma terms. Its retrieval prefixes are `task: search result | query: ` and `title: none | text: `, with a 2,048-token model context and 768-dimensional full embeddings. Preserve the same document recipe across corpus/query retrieval. The ggml-org repository currently publishes Q8_0 only: do not label it Q4 or use the ONNX Q4 file in llama.cpp. [Google card](https://huggingface.co/google/embeddinggemma-300m), [GGUF publisher](https://huggingface.co/ggml-org/embeddinggemma-300M-GGUF).

QVAC's embeddings engine accepts llama.cpp-compatible GGUF. The Q4 publisher artifact must still be load-tested for this engine. Rebuild every corpus vector with the selected GGUF engine/config/prefixes; **never reuse the existing ONNX corpus vectors for GGUF queries**, even if model name and 768 dimensions match. Record artifact hash, runtime, normalization, document recipe and corpus fingerprint in a new manifest. This compatibility rule is an engineering requirement, not a claim that cross-runtime numeric equivalence was measured. [QVAC embeddings](https://docs.qvac.tether.io/sdk/ai-capabilities/text-embeddings/).

## Offline and P2P audit

Local file sources avoid HTTP/registry source resolution in the inspected source. The registry client is created lazily through `getRegistryClient()` and can initialize Hyperswarm when that branch is used. Engine initialization itself sets environment, locks and native resource collection; this inspection does not establish zero network attempts across every plugin, native addon or startup action. [Local source resolution](https://github.com/tetherto/qvac/blob/ffff93cc7c31ea12c547c4b6bbfce4168f6a8e2c/packages/inference/src/handlers/load-model/resolve.ts), [registry initialization](https://github.com/tetherto/qvac/blob/ffff93cc7c31ea12c547c4b6bbfce4168f6a8e2c/packages/inference/src/runtime/registry-client.ts), [engine lifecycle](https://github.com/tetherto/qvac/blob/ffff93cc7c31ea12c547c4b6bbfce4168f6a8e2c/packages/inference/src/runtime/lifecycle.ts).

No documented global `offline:true` or P2P-disable setting was verified. `swarmRelays:[]` controls relays and is not proof that DNS/DHT networking is disabled. `requireHttpChecksum` and `requireSecureTransport` harden downloads, not network isolation. Preparation must explicitly download pinned files and verify SHA-256 before serving; serving must fail for missing files instead of discovering/downloading replacements.

Audit the actual installed/pinned runtime with non-loopback DNS/socket connections denied while loopback HTTP/IPC remains allowed. Include cold startup, fresh semantic query, fresh draft/rewrite, malformed output, missing-model behavior, restart and review persistence. Python/browser guards alone do not cover the separate Node/Bare/native process. The evidence must distinguish denied attempts from no attempted connections and process isolation from a physical Wi-Fi rehearsal. Do not disable the user's Wi-Fi.

## Remaining runtime evidence

Outstanding: installed lockfile versions/native ABI, `qvac doctor`, Vulkan device enumeration and GPU placement, actual GGUF loads, strict schema behavior, prefix/vector quality, latency, combined memory, bounded cancellation/retries and external-connection audit. A package listing, model file hash or successful `/v1/models` call alone does not prove fresh offline generation. This note recommends the candidates and contract; it does not certify G10 completion or the historical ONNX benchmark for GGUF.
