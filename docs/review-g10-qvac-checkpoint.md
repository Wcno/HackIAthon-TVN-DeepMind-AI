# QVAC checkpoint review

Reviewed before push, 2026-10-08. Fixed base `06cb2166720d58a25fc7c783a0d3ad126187acfc`, implementation checkpoint `0080e91d8ae5ef17d6073f31f057ffe5bc2f44a4`. Command: `git diff 06cb216...0080e91`; one WIP implementation commit. Two independent review agents examined Standards and Spec. The user stopped development and requested a checkpoint for another agent; these findings are deliberately carried forward instead of continuing implementation.

## Standards

**Hard documented violations: 0.** The user's QVAC requirement supersedes the earlier no-local-model decision; the handoff explicitly records the pending ADR updates and incomplete validation.

**Heuristic finding — possible Mysterious Name:** `src/whoami/backend/app.py:204` assigns either provider to `app.state.gemini`:

```python
app.state.gemini = provider(repository, settings, transport=gemini_transport)
```

This value can now be a `QvacClient`, while downstream adapters and arguments retain Gemini-specific names. That obscures which provider owns generation and complicates future provider changes. In subsequent development, use a neutral generator name and clarify the shared client interface. This is a maintainability judgment, not a hard rule or checkpoint blocker.

**Known unresolved correctness risk:** `src/whoami/backend/qvac.py` inserts a constant `GENERATOR_SHA256` into cache identity without verifying the model actually served by the endpoint. Replacing weights under the same endpoint/alias can reuse incompatible cached results. The handoff already identifies runtime model verification as a required next step.

No edits or model calls performed. This review supports preserving the documented WIP checkpoint; it does not establish readiness to merge.

## Spec

Checkpoint WIP adecuado para entregar a otro agente; **sin impedimento para subirlo como trabajo incompleto**.

Pendientes de traspaso frente a «Implementa qvac para funcione al 100% el g10»:

- **Runtime portable:** `src/whoami/qvac_runtime/package.json` fija dependencias, pero faltan instalador, worker y comandos reproducibles. El handoff lo declara: «There is no installer, launcher, packaged worker or `qvac-demo` command yet».
- **Identidad del modelo:** `src/whoami/backend/qvac.py` incorpora `GENERATOR_SHA256` al caché sin comprobar qué modelo sirve el alias. La siguiente implementación debe resolver «Check model identity rather than assuming any process at the configured alias serves this GGUF».
- **Aceptación completa:** los tests usan respuestas HTTP inyectadas; faltan generación editorial real, aislamiento del proceso Node/Bare, browser, Windows/Linux y evidencia T10/Notion. Todos figuran explícitamente pendientes.

No encontré cambio silencioso de proveedor cloud, mezcla de embeddings GGUF/ONNX ni afirmación de G10 completo. La documentación conserva el alcance correcto de la orden más reciente: «Development stopped at the user's explicit request» y «Do not merge this checkpoint, close G10, or describe it as complete».

No corresponde continuar implementando estos pendientes antes de subir el checkpoint autorizado.

## Checkpoint disposition

Standards: 0 hard violations, 1 maintainability heuristic and 1 unresolved model-identity risk. Spec: 3 partial final-delivery requirements. The worst Standards risk is unverified model identity; the largest Spec gap is the missing reproducible runtime and full acceptance evidence. Publish as a draft checkpoint only, with no merge or issue closure.
