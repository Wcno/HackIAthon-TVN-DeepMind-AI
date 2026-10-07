# Contract between lanes: screens and data (G2)

What each screen shows, which data it needs and who produces it. The schemas are code:
`src/whoami/schemas.py` (Pydantic v2, validated on construction), vocabularies and paths in
`src/whoami/contracts.py`, reading and writing in `src/whoami/store.py`.

Python names are English. Field names and values in the data files follow §7 and the challenge vocabulary, so they
stay in Spanish (`id_caso`, `estado_evidencia`, `puntaje`, `afirmaciones`…).

## Lanes and files

```text
G1 ingest ──▶ data/processed/noticias.csv, indicadores.csv, indicadores_inec.csv, eventos.geojson,
              fuentes.json, calidad_*.json, data/manifest.json                       (already exist)
G3 ai     ──▶ data/processed/grupos.jsonl      Group: members, score, official context
              data/processed/evidencias.jsonl  Evidence: everything that can be cited
G4 ai     ──▶ outputs/fichas.jsonl             CaseFile: §7
              outputs/consultas.jsonl          Answer: precomputed answers (offline, D-01)
G5 api    ──▶ outputs/revisiones.jsonl         ReviewRecord: history of human decisions (append-only)
G6 front  ◀── reads everything through the G5 API
```

Until G3 and G4 exist, **`data/demo/` holds a synthetic set with the same files and schemas**. The interface switches
between demo and real data by changing a directory:

```python
from whoami.store import load, load_demo

output = load_demo()  # synthetic set, everything in data/demo/
output = load()       # real pipeline: groups and evidence from data/processed/, the rest from outputs/
output.grupos         # tuple[Group, ...], already in inbox order
output.evidencias     # dict[id_evidencia, Evidence]
output.review_state("CASO-001")
```

`load` and `write` reject the whole set when a schema or a rule between records breaks (see `verify` below). Run
`uv run whoami demo` to regenerate `data/demo/`. The demo news are invented (`sintetico: true`, URLs on the reserved
`demo.invalid` domain); the World Bank, INEC and USGS figures are the real ones from `data/processed/`. Nothing in the
demo comes from a model, so it says nothing about the quality of the real pipeline. The interface must show a notice
while `sintetico` is true.

## Screens and the data each one needs

Stages are those of §3. Show Panama time everywhere: data travels in UTC (`…Z`) and the interface converts.

| # | Screen (stage) | Shows | Data it needs | Source |
|---|---|---|---|---|
| 1 | **Quality report** (1 Load) | What came in, what was excluded and why; nulls kept; coverage by source; snapshot integrity | `ventana`, `registros_leidos`, `incluidas`, `excluidas_por_motivo`, `cobertura_por_fuente` from `calidad_noticias.json`; `filas_*` from `calidad_indicadores.json`, `calidad_inec.json`, `calidad_eventos.json`; `version`, `fecha_corte_UTC`, `sha256` from `manifest.json` | G1, existing files (no new schema) |
| 2 | **Prioritised inbox** (2-4) | Groups ordered by score, with components, range and evidence state | `Group`: `titulo`, `tema` (label in `TOPIC_LABELS`), `puntaje` (`valor`, `rango`, `componentes`, `version_reglas`), `estado_evidencia`, `n_noticias`, `n_medios`, `n_procedencias`, `id_caso`; review state from `output.review_state(id_caso)` | G3 → `grupos.jsonl`, G5 → `revisiones.jsonl` |
| 3 | **News group** (2) | Members, outlets versus independent provenances, recirculated news with their original date | `Group.miembros`: `titulo`, `url`, `medio`, `procedencia`, `fecha_publicacion`, `alcance_texto`, `recirculada_en` | G3 → `grupos.jsonl` |
| 4 | **Official context** (3) | Linked indicator or earthquake with period, unit and limitations; or why there is no link | `Group.contexto` (`etiqueta`, `pais`, `limitaciones`, `razon`) and, from its `Evidence.campos`, `periodo`, `unidad` and `valor`. Without a link, `sin_contexto_motivo` | G3 → `grupos.jsonl` + `evidencias.jsonl` |
| 5 | **Evidence file** (5 Explain) | What is reported and by whom; what is backed; what is missing; contradictions; recommended action; navigable citations | `CaseFile`: `afirmaciones` (`tipo`, `atribuida_a`, `citas`), `vacios`, `contradicciones`, `accion_recomendada`, `alcance_texto`; each `Citation` opens with its `Evidence` (`url`, `fecha`, `campos`). Score and evidence state come from the group (`id_grupo`) | G4 → `fichas.jsonl` + `evidencias.jsonl` |
| 6 | **Editorial package** (6 Produce) | Brief, title, angle, 3 questions, sources and checks, script, copy; facts, statements, inferences and hypotheses told apart | `CaseFile.borrador` (`EditorialPackage`, including `leyenda`) and `CaseFile.afirmaciones[].tipo`. `borrador` is null when there is not enough evidence to write | G4 → `fichas.jsonl` |
| 7 | **Human review** (7 Review) | Current state, person responsible, date, note and history; state change | `ReviewRecord`: `id_caso`, `estado`, `responsable`, `fecha`, `nota`. The current state is the record with the latest `fecha` | G5 → `revisiones.jsonl` |
| 8 | **Query box** | Answer with citations, or abstention with what is missing, or both versions of a contradiction | `Answer`: `estado`, `respuesta`, `citas`, `motivo_abstencion`, `faltante`, `versiones`. Offline it only answers the precomputed ones (D-01) | G4 → `consultas.jsonl` |

## One place per fact

- **Review state** lives only in `revisiones.jsonl`. Neither `Group` nor `CaseFile` stores it. The current state is
  the latest record by `fecha` (equal dates keep file order); a case with no records is `nuevo`. Adding a review never
  forces G3 or G4 to rewrite their files.
- **Score, evidence state, title and topic** of a case file are read from its group. `CaseFile` only keeps `id_grupo`.
- **Period, unit and value** of an official figure are read from its `Evidence`. `ContextLink` points to it.
- §7 still wants some of these inside `fichas.jsonl`, so `store.case_file_to_record` copies them **when exporting**:
  `ids_fuente` (the cited evidence), `citas` (flat, no duplicates), `puntaje`, `componentes`, `estado_evidencia`,
  `estado_revision`, plus `puntaje_detalle`, `titulo` and `tema`. They are ignored when loading, so they cannot drift.

## Allowed review transitions

Every case starts in `nuevo`. Nothing goes back to `nuevo`, and a state cannot repeat.

| From | To |
|---|---|
| `nuevo` | `en_revision`, `requiere_evidencia`, `descartado` |
| `en_revision` | `requiere_evidencia`, `aprobado_como_borrador`, `descartado` |
| `requiere_evidencia` | `en_revision`, `descartado` |
| `aprobado_como_borrador` | `en_revision`, `descartado` |
| `descartado` | `en_revision` (a discarded case must be reopened before it can be approved) |

## Rules enforced in code

Building an invalid record raises `ValueError` (Pydantic's `ValidationError` is one), so no lane hands over something
another lane has to distrust. Models are frozen and reject unknown fields, and field types are checked.

- **Score:** `P = 30R + 25I + 20U + 15N + 10E`, components in 0-1. Value and range are **derived** from the
  components and not accepted from outside. The five components carry a justification, and the rules version.
  Ranges, no overlap: `bajo [0,40)`, `medio [40,70)`, `alto [70,100]`. Ties: higher `U`, then `id_grupo`
  (`sort_inbox`).
- **Citations:** every claim cites at least one piece of evidence. `citation_errors` checks that the id exists, the
  field exists and the passage is **literal**; it is the base of G4's deterministic verifier.
- **Statements:** a claim of type `declaracion` needs `atribuida_a`. Accusations are never facts.
- **Dates:** ISO 8601 and real UTC (`2026-13-45T99:00:00Z` and offsets other than `Z` are rejected).
- **Headline only:** if `alcance_texto` is `titular_metadatos`, the draft carries the legend
  «basado únicamente en titular/metadatos».
- **Editorial package:** brief ≤ 250 words, copy ≤ 80, exactly 3 questions.
- **Provenances:** `n_procedencias` counts distinct origins; an agency republished by three outlets is one.
- **Official context:** a group has context or says why not (`sin_contexto_motivo`), never both; no link is forced.
- **Recirculated news:** `fecha_publicacion` is the original; `recirculada_en` is later (T03).
- **Review:** any state other than `nuevo` names a person responsible.

`verify(output)` checks what no single record can see, and lists every problem it finds:

- every citation resolves to an existing evidence and a literal passage;
- a case file only cites evidence of its own group (its members and its official context);
- every member and context link has an `Evidence`, and official evidence carries `periodo`, `unidad` and `valor`
  (`valor` may be empty when the source value is null: it is never filled with zero);
- a case file and its group point at each other (`id_caso`);
- if the evidence is not `suficiente_para_borrador`, `vacios` says what is missing;
- a review exists only for a case with a case file; every change follows the transitions above;
- **high priority with insufficient evidence cannot be approved**, and nothing is approved without a draft.

## `fichas.jsonl` (§7)

The minimum fields come first, in the order the challenge lists them: `id_caso`, `modalidad`, `ids_fuente`,
`afirmaciones`, `citas`, `puntaje` (a number), `componentes` (`R`, `I`, `U`, `N`, `E`), `estado_evidencia`,
`borrador`, `estado_revision`. Then the fields the screens need: `puntaje_detalle` (`rango`, `version_reglas`,
`justificaciones`), `titulo`, `tema`, `id_grupo`, `alcance_texto`, `vacios`, `contradicciones`,
`accion_recomendada`, `sintetico`.

## Decisions other lanes need to know

- **Topics:** the contract uses slugs (`economia`, `logistica_canal`, `turismo`, `servicios_publicos`,
  `eventos_naturales`, `regulacion`, plus `sin_tema`). The classifier in `src/ai` currently returns the PDF labels
  (`"economía"`, `"logística/Canal"`…) and must map them to these slugs. Display names are in `TOPIC_LABELS`.
- **Evidence ids:** `N-<hash>` (news), `WB-<country>-<indicator>-<year>`, `INEC-<series>-<period>` and `USGS-<id>`.
  The prefix must match the type.
- **Components R and I** are decided by G3; this contract only requires them to be in 0-1 and justified.
- **No forced link:** a USGS earthquake is only linked to a news item about that earthquake. In the demo, group
  `G-006` is a December 2025 story recirculated in October 2026, linked to the quake of that same date (T03 and USGS
  context at once).
- **Review persistence (G5):** this contract defines the record and the transitions; where it is stored is up to G5.
