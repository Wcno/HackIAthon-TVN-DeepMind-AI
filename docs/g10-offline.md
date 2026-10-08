# G10: offline demonstration

The delivery freezes the existing corpus, groups, scoring components, evidence,
case files, drafts, reviews and precomputed queries. The 35 saved questions plus
missing development benchmark questions produce 48 distinct query IDs covering
all 40 public development cases. It also includes corpus vectors, quality reports,
local photos, fonts, CSS and JavaScript. Credentials, caches, ONNX models, raw
captures and G7's private held-out benchmark are excluded.

The file outputs/offline/benchmark-consultas.jsonl preserves 39 replies from
outputs/evaluation/g7-final/answers.jsonl, revalidated against current evidence.
An ID already present in outputs/consultas.jsonl retains its current reply.
D-C08 needs two synthetic sources absent from the editorial snapshot: its offline
reply abstains and explains the missing input. Those sources are not invented or
added to real news. This availability adaptation changes neither historical
captures nor G7 metrics. Development labels remain proposals pending human review.

## Prepare before disconnecting

Install the application and dependencies first:

~~~powershell
uv sync --locked --link-mode copy
uv run --locked whoami offline-demo prepare --output offline-demo
uv run --locked whoami offline-demo verify --bundle offline-demo
~~~

Preparation copies existing results; it never calls Gemini or recalculates the
pipeline. It rejects incomplete input, broken hashes, stale vectors, fewer than
five drafts, or missing answered/abstained queries. The 22 news records without a
publication date stay in the corpus but are excluded from pipeline vectors, as
required by G1/G3's publication-date contract.

For a changed corpus, finish "whoami download-model", "whoami embed",
"whoami pipeline" and "whoami generar" before packaging. Those preparation
commands follow G3/G4's provider configuration and quotas. G10 never runs them
implicitly or uses held-out questions for tuning. Rebuild the data manifest after
changing its covered files. An existing destination is never overwritten; choose
a new directory for a new snapshot.

Copy the bundle to a machine with the same application and dependencies already
installed. The original repository path and a local model are unnecessary. To
start without letting uv synchronize dependencies, use the installed executable:

~~~powershell
.venv\Scripts\whoami.exe offline-demo serve --bundle offline-demo
~~~

Linux: .venv/bin/whoami offline-demo serve --bundle offline-demo.
Open http://127.0.0.1:8000/inbox; --port selects another port.

The serve command validates the bundle before starting, forces offline mode and
ignores online settings/API keys from .env. No model is downloaded or loaded.
Co-News uses local BM25 source search and existing gaps/contradictions.
New Gemini drafts or rewrites return an availability explanation. Saved questions
show verified citations or an abstention; unknown questions show
«Sin conexión: solo se responden las consultas precalculadas». Original article
links need connectivity if opened; their stored passages remain available at
/evidence/... inside the app.

## Seven stages and persistence

1. **Calidad:** snapshot date, sources, gaps and verified integrity.
2. **Agenda:** precomputed priority, components and TVN coverage.
3. **Cobertura:** group members and independent sources.
4. **Contexto:** stored indicators/events with period and unit.
5. **Historia:** accepted claims, citations and gaps in a saved case file.
6. **Borrador:** saved draft, human editing and local source search.
7. **Revisión:** reviewer, note and state, without automatic publication.

In Consultas, choose a useful reply and an abstention, then try an unknown
question. Mutable SQLite is stored at offline-demo/runtime/editorial.sqlite3,
outside the hashed seed. --database chooses another location. Restarting with
the same bundle/database preserves human edits and reviews; do not delete that
directory for a repeat rehearsal. Use a new bundle or database for a clean run.

## Reproducible evidence

~~~powershell
uv run --locked playwright install chromium
uv run --locked python scripts/validate_g10.py --browser --output outputs/validation/g10-rehearsal
~~~

The rehearsal starts a real process with deliberately online ambient settings
and a dummy key; serve overrides them. The child rejects non-loopback DNS/socket
connections and embedder construction. The browser aborts every external origin.
It exercises seven stages, all 48 questions, unknown-query fallback, generation
refusal, BM25 search, browser editing and review persistence after process restart.
It saves report.json, zero-attempt isolation audits and desktop/mobile screenshots.
It does not toggle the host's Wi-Fi: the report explicitly distinguishes process
isolation from a physical Wi-Fi rehearsal.

To use installed Edge on Windows, set PLAYWRIGHT_CHROMIUM_EXECUTABLE to
C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe.
CI runs the same rehearsal with Chromium on Windows and Linux and uploads its
reports/screenshots. The Notion mirror records T10 in
docs/notion/06-pruebas-y-metricas.md. Per D-05, the team manually copies evidence
to native Notion and records the physical Wi-Fi rehearsal before the pitch.
