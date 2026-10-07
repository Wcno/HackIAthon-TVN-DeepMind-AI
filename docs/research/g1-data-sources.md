# G1 - Data sources audit and recommendation

Issue: Wcno/hackiaton-whoamisfc#19 (`gh issue view 19`).
Live checks run on 2026-10-06/07 from this machine.
Evidence tags: `branch:path` = repo file, URL = live check.

## 1. TL;DR - recommended set (ranked)

1. **TVN sitemaps (monthly `contents_YYYY_MM`)** - the only source with a full-year archive (2025-10 to 2026-10 all present). Anchor of the corpus. Effort low (code exists). Needs publication date from page metadata, because sitemap gives only `lastmod`.
2. **Official WordPress feeds (ACP, SINAPROC, MEF, MICI, ATP, AMP)** - full-year history via `wp-json` with `after=`; clean `date_gmt`, categories. Gives the "second origin" and the context for CU-01/CU-02/CU-05. Effort low (code exists).
3. **Banco Mundial (6x6x15)** - works today, CC BY 4.0, already raw-frozen. Effort low. Required by CU-02/T04.
4. **USGS sismos** - works today, public domain. Raw is stale (2024); re-pull for the D-02 window (88 events). Effort low.
5. **INEC IPC + PIB trimestral (CSV/XLSX only, not the 309-page PDF)** - the one official national numeric source, CC BY 4.0, serves T04 and the planted conflicts. Effort medium. Take 2-3 files, not the catalog.
6. **2-3 extra news outlets (Telemetro, La Prensa, Panama America) for CU-03** - this is the real gap, see section 5. Their news sitemaps and RSS only cover about 2 days, so they only work for the last weeks via daily capture or GDELT.

Optional only if time allows: GDELT (currently blocked, 3-month window, see section 3).
Skip: SBP, ACP annual report PDF, ATP PDF, IMHPA PDFs, Gaceta Oficial, bank sites.

## 2. Findings from `prod` and `NoSkill`

### `NoSkill` (35c412c "scraping general de 22 fuentes panamenas")

- Code: `NoSkill:src/senal/ingest/{_crudo,tvn_sitemap,medios,usgs,worldbank}.py`, `NoSkill:src/senal/contracts.py`, `NoSkill:scripts/captura_tvn.py`.
- `medios.py` registers 22 sources over three ways: `wp_api`, `news_sitemap`, `rss`. Stdlib only, 1.2 s politeness pause (`NoSkill:src/senal/ingest/medios.py`).
- Frozen raw: `NoSkill:data/raw/medios/_indice.jsonl` (1,948 rows), `NoSkill:data/raw/tvn_sitemap/_indice_ventana.jsonl` (8,012 rows, 90-day window), `NoSkill:data/raw/usgs/eventos_2024.geojson` (82 events), `NoSkill:data/raw/worldbank/*.json` (6 files x 90 rows, 0 nulls, lastupdated 2026-07-13).
- Per-source counts and `licencia` strings: `NoSkill:data/raw/medios/_consultas.json`.
  News sitemaps: prensa 100, midiario 54, laestrella 131, metrolibre 145, ecotv 41, telemetro 181.
  RSS: panamaamerica 22, diaadia 10, critica 10, tvn 150.
  WP API: foco, pancanal, amp, mici, mef, contraloria, acodeco, atp, sinaproc, banconal, abp (about 100 each, a page cap, not the full history).
- Limits: it is a snapshot of the last ~2 days for news (docstring says so), 90 days for TVN, not the D-02 window. No GDELT. No `data/processed/` and no normalizer to `noticias.csv`.
- Reusable as is: `_crudo.py` (raw+SHA-256+`_consultas.json` pattern), `tvn_sitemap.py`, `medios.py`, `worldbank.py`, `usgs.py`.

### `prod` (61fc47e "consolidar plan TVN Signal")

- Same `_crudo/tvn_sitemap/usgs/worldbank` modules, but no `medios.py` (`git ls-tree origin/prod`).
- Adds `prod:data/preparacion_tvn/` (171 TVN articles with date read from page metadata, 129 inside 2025-10-02..2026-09-30), `prod:scripts/verificar_metadatos_tvn.py` (1 req/s, reads publication date from HTML metadata), `prod:scripts/auditar_corpus_tvn.py`.
- `prod:data/preparacion_tvn/README.md`: coverage is "mostly July-Sept 2026", not annual, not multi-outlet. GDELT had 4 timeouts and 1 empty answer (`prod:data/preparacion_tvn/resumen.json`).
- `prod:data/fuentes_adicionales_tvn.json` and `prod:docs/research/fuentes-oficiales-tvn.md`: INEC/ACP/ATP/SINAPROC/IMHPA/Gaceta candidates with license notes and priority P0-P2 (INEC P0).
- `prod:docs/PLAN.md` (B02/B03): period is 2025-10-02 to 2026-09-30 Panama time; planned modules `ingest/{base,tvn,gdelt,generic_rss}.py`; gate is at least 100 unique news and at least 20 TVN; "do not inflate corpus with bulletins".
- Merge note: `NoSkill` has `medios.py` and WP/sitemap raw; `prod` has the date-verification script and the official-source research. Neither has `data/processed/`.

## 3. Candidate source table

Window = D-02 (2025-10-02 onward; PLAN says through 2026-09-30). Effort = ingestion effort.

| Source | Content | Access | License | Freshness / window coverage | Effort | Requirement | Verdict |
|---|---|---|---|---|---|---|---|
| TVN monthly sitemaps | Title (in `image:title`), URL, section, `lastmod`; no body | XML. Index lists `contents_2008_09` to `contents_2026_10` (https://www.tvn-2.com/tvn_sitemap_index.xml). Nov 2025 file has 1,797 URLs (https://www.tvn-2.com/tvn_sitemap_contents_2025_11.xml) | No reuse terms; site terms forbid copying content, keep metadata only (`NoSkill:data/raw/tvn_sitemap/_consultas.json`). robots allows (https://www.tvn-2.com/robots.txt) | Full window. `lastmod` is not publication date | Low + date verification (med) | CU-01..05, T01-T03, 20 TVN gate | **use** |
| TVN RSS | 150 recent items with real pubDate | RSS (https://www.tvn-2.com/rss/, HTTP 200) | Same as above | About 17 h history (`NoSkill:scripts/captura_tvn.py`) | Low | Date calibration, live top-up | maybe (use to verify dates only) |
| Official WP feeds: pancanal, sinaproc, mef, mici, atp, amp | Press releases, `date_gmt`, categories | `wp-json/wp/v2/posts?after=2025-10-02`. Totals since 2025-10-02: sinaproc 307, mici 330, mef 210, pancanal 121, amp 115, atp 73 (live `X-WP-Total`) | Press releases of public bodies; per-site reuse not stated, keep metadata+short quote (`NoSkill:data/raw/medios/_consultas.json`). ACP terms restrict copying (`prod:docs/research/fuentes-oficiales-tvn.md`) | Full window via pagination | Low | CU-01, CU-02, CU-05, T04 context, second origin | **use** (those 6) |
| WP feeds: contraloria, acodeco, banconal, abp | Same | Same | Same | Same | Low | Marginal | skip |
| Banco Mundial API v2 | 6 countries x 6 indicators x 2010-2024 | JSON API (live HTTP 200, lastupdated 2026-07-13) | CC BY 4.0 (https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) | Annual, outside D-02 by design | Low (done) | CU-02, T04, T01 | **use** |
| USGS FDSN | Earthquakes, box lat 5-12, lon -86..-76, M3+ | GeoJSON (live count for 2025-10-02..2026-10-06 = 88) | Public domain, credit USGS (`NoSkill:data/raw/usgs/_consultas.json`) | Re-pull for window; raw is 2024 | Low | `eventos.geojson`, eventos_naturales | **use** |
| INEC IPC / PIB / EML | CPI, quarterly GDP, labour survey | CSV/XLSX/PDF on inec.gob.pa. IPC Aug 2026 published 2026-09-14 | CC BY 4.0 stated on catalog page (https://www.inec.gob.pa/avance/Default2.aspx?ID_CATEGORIA=2&ID_CIFRAS=10&ID_IDIOMA=1) | Monthly/quarterly to Aug 2026 | Med (`;` delimiter, non-UTF-8 CSV, multi-row headers per `prod:docs/research/fuentes-oficiales-tvn.md`) | CU-02, T04, contradictions (T05) | **use** (IPC Cuadro 2 CSV, IPC Anexo 4 XLSX, PIB trimestral CSV only) |
| Other outlets: La Prensa, Mi Diario, La Estrella, Metro Libre, ECO TV, Telemetro | Title, URL, `news:publication_date` | Google News sitemap | No terms found; metadata only (`NoSkill:data/raw/medios/_consultas.json`) | About 2 days by spec; 41-181 items each on 2026-10-07 | Low per source | CU-03 independence | **use for the last weeks only**; pick 3 (Telemetro, La Prensa, Panama America) |
| Panama America, Dia a Dia, Critica RSS | 10-22 items with date | RSS | Same | Hours to days | Low | CU-03 | maybe (Panama America yes; Dia a Dia and Critica skip) |
| Telemetro full news sitemaps | Possible archive | `sitemap/news-full/sitemap-index.xml` (live, lists `.gz` files with lastmod 2024-02-16) | No terms found | Unverified: may end in 2024 | Med | Backfill CU-03 | maybe, one-hour spike only |
| GDELT DOC 2.0 | Cross-outlet URLs, `seendate` | `api.gdeltproject.org/api/v2/doc/doc` | Not stated; does not transfer media rights (`docs/challenge/06-datos-publicos.md`) | **Rolling 3 months only**, max 250/query (https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/). Live: HTTP 429 on 4 spaced calls here; prod saw timeouts | Med-high (rate limit 1 req/5 s) | PDF source A, `fecha_deteccion` | maybe: try once, freeze result, do not block on it |

## 4. Skipped sources and why

- SBP (superbancos.gob.pa): bank modality is out of scope (`prod:docs/PLAN.md` line 7).
- ACP annual report PDF and statistics page (Power BI): terms restrict copying, license unconfirmed (`prod:docs/research/fuentes-oficiales-tvn.md`). Use the WP press releases instead.
- ATP statistics PDF: license unconfirmed, mixes INEC and STR data.
- IMHPA bulletins: HTTP 403 for the research agent, license unconfirmed. SINAPROC feed covers weather alerts.
- Gaceta Oficial: only worth it per chosen story, no general license verified. Skip for MVP.
- INEC EML 309-page PDF: heavy extraction, period inconsistency (title August, text September/October). Keep only as a T05 fixture if wanted.
- Contraloria, ACODECO, Banconal, ABP feeds and Foco, ECO TV, Metro Libre, Mi Diario, Dia a Dia, Critica: add volume, no new requirement coverage. More sources means more raw to dedupe and QA.
- Local models and paid APIs: out of scope (ADR 0001).

## 5. Gaps and open questions

1. **CU-03 multi-outlet inside the window.**
   Only TVN has a year archive.
   Other outlets expose about 2 days (news sitemaps) and GDELT only 3 months, so Oct 2025 to Jun 2026 has no second news outlet.
   Options: (a) accept a multi-outlet "recent slice" (about Jul-Sep 2026 via GDELT if it works, plus daily captures) and say so on the coverage panel; (b) test Telemetro archive sitemaps; (c) use official WP feeds as the second origin for events (ACP, SINAPROC, MEF) and call them official, not independent media.
   Decision needed from the team.
2. **Publication date for TVN.** Sitemap has `lastmod` only. `prod:scripts/verificar_metadatos_tvn.py` fetches 1 page/s: about 3,000 articles per month would take about 50 min per month. Decide: verify only topic candidates (as prod did, 171) or a sampled/filtered set.
3. **GDELT is blocked or slow right now** (HTTP 429 after waits, timeouts on prod). Freeze one good pull early, or drop it. If dropped, `fecha_deteccion` stays empty and the team should say so, since the PDF names GDELT.
4. **Window end.** Issue says "from 2025-10-02", PLAN says through 2026-09-30. Today's data (Oct 2026) would be excluded. Confirm 2026-09-30.
5. **Window vs. 2024 USGS file.** Existing USGS raw is 2024 and outside D-02; re-pull required.
6. **Rights.** No outlet publishes reuse terms; keep metadata only (title, URL, date, section) and mark `alcance_texto = titular_metadatos`. INEC and World Bank are the only clearly open sources.
7. **Counts to hit gates:** at least 100 unique news and at least 20 TVN. TVN alone exceeds both; the open point is independent origins, not volume.

## 6. Suggested ingestion order

1. Merge `NoSkill` ingest modules with `prod` date verification; one module per source under `src/senal/ingest/`.
2. World Bank and USGS (re-pull 2025-10-02..2026-09-30): minutes, unlocks `indicadores.csv` and `eventos.geojson`.
3. TVN monthly sitemaps for 2025-10 to 2026-09 + date verification on topic candidates, then `noticias.csv`, `excluded` with reason, quality report, `manifest.json` with SHA-256 (T01).
4. Official WP feeds (6 sources, `after=2025-10-02`), tagged by `tema_probable` and `es_agencia=False`.
5. INEC 3 files (IPC Cuadro 2, IPC Anexo 4, PIB trimestral CSV), normalized to a small table with unit, base and period.
6. Other outlets: freeze one capture of Telemetro, La Prensa, Panama America now, and schedule `scripts/captura_tvn.py`-style captures until the demo (about 30 min cadence).
7. GDELT: one throttled attempt (1 req/5 s, by day, filter `sourcecountry:PM`); keep the result if it works, otherwise record `coverage_gap`.
