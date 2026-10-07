# TVN publication date: is sitemap `lastmod` good enough?

Measured on 2026-10-06/07.
Scripts and samples live outside the repo (scratchpad), nothing in `src/` or `data/` was touched.

## TL;DR

**Recommendation: hybrid.**
Use `lastmod` as `fecha_publicacion` for almost everything, and fetch the page only for the small set of suspicious items (about 0.25%, roughly 75 pages).

- In a stratified sample of 260 pages, `lastmod` was never earlier than the true publication date and never more than 6.05 h later.
  100% were within 1 day, 93.8% within 1 hour, 75.4% exact to the minute.
- The sitemap does hide a tail of republished or edited old articles.
  In the Sep 2026 file, 41 items have ids far below the month's range.
  Of 20 such items fetched, 13 were published more than 1 day before `lastmod` (up to 2013).
- Those items are detectable without fetching, because their id is far below the month's id range.
  Fetching only them costs about 2 minutes at 1 req/s.
- Interpolating a date from the id is worse than `lastmod` (median error 4 h, p90 13 h) and adds nothing.
  Fetching all 29,881 pages costs 8.3 h at the 1 req/s floor, about 21 h at the rate observed here.
- Tradeoff: the hybrid accepts a residual error of roughly 0.1% of items (older items that look normal by id), in exchange for about 99.7% fewer fetches.

## Measurements

### 1. `lastmod` versus true publication date

Method: 20 random URLs per monthly sitemap, 13 months, 260 pages, seed 42, 1 req/s, descriptive User-Agent, 0 errors.
Source: `data/raw/news/tvn/tvn_sitemap/contents_YYYY_MM.xml`.
True date: JSON-LD `datePublished`, falling back to `article:published_time` (needed for 52 of 260 pages, mostly `videos` and `jelou`, where JSON-LD has no `datePublished`).
Example page: https://www.tvn-2.com/nacionales/judicial/caso-pandora-declaran-legal-aprehension-exjecutivo-bancario-autoriza-pagos-fiscales-dgi_1_2264701.html

| Metric (lastmod - published) | Value |
|---|---|
| Negative differences | 0 of 260 |
| Median | under 1 s |
| p75 | 56 s |
| p90 | 30 min |
| p95 | 2.2 h |
| Max | 6.05 h |
| Within 1 hour | 93.8% |
| Within 1 day | 100% |
| Different calendar month (UTC) | 1 of 260 (0.4%) |
| Different calendar month (America/Panama, UTC-5) | 0 of 260 |
| Every month, every section (nacionales, tvmax, mundo, videos, entretenimiento) | median under 2 min, 100% within 1 day |

In the outlier sample the page's JSON-LD `dateModified` equals the sitemap `lastmod` to the second.
So `lastmod` is the page's last edit time, and for most articles that is the publication time.

Cross-check on the 95 RSS items in `data/processed/noticias.csv` that have both fields: median gap 0 h, p90 2.9 h, max 70.8 h.
Only 99 rows have `fecha_publicacion` and 4 of them have no `fecha_modificacion`.

### The tail: old articles republished or edited

A month file holds items whose ids are almost disjoint from other months (id p1 to p99 do not overlap, see `contents_*.xml` ids).
A few items are far outside their month's range.
Rule used: id more than 300 below the previous month's p99 id.
It flags 74 of 29,955 sitemap items (0.25%).
Counts by file: 2026_09 has 41, 2026_05 has 6, the rest 1 to 4.
I fetched 20 of them at random:

| Result | Count |
|---|---|
| Published more than 1 day before `lastmod` | 13 of 20 |
| Published months or years earlier (e.g. 2025-06-01, 2025-07-30, 2013-06-21) | 3 of 20 |
| 1 to 30 days earlier | 10 of 20 |
| Within 1 day of `lastmod` | 7 of 20 |

Many of the Sep 2026 ones were edited in one batch around 2026-09-04 03:00 UTC, and their JSON-LD has no `datePublished`, only `article:published_time`.
Two of the 260 random items were published before the window start 2025-10-02 (Oct 2025 file edge), and the outlier sample has items from 2025-06 and 2025-07 inside 2026 files, so a window filter on `lastmod` leaks a few old items.

### 2. Is the id monotonic with publication date?

Mostly, yes, but with noise.

- Ids in the URL (`_1_2264701.html`) rise with time: about 3,900 to 4,500 new ids per month, month ranges barely overlap.
- In the 260-sample sorted by id, publication time goes backwards 7 times out of 259 pairs.
- Linear interpolation between neighbouring anchors (leave-one-out over the 260 fetched pages): median error 4.0 h, p90 13.4 h, p99 25.7 h, 98.1% within 1 day, 66.7% within 6 h.
- Half-split (train on 130, test on 130, 200 repeats): median 5.3 h, p90 15.4 h, 97.6% within 1 day.
- This is 100x to 1000x worse than `lastmod` for normal items.
  Its only useful role is outlier detection: an item whose id disagrees with its `lastmod` month is suspicious.
- Anchors from RSS are few (147 items in the single capture `data/raw/news/tvn/rss/capture_20261007T033304Z.xml`) and cover only the last day, so they add nothing.

### 3. Other machine channels

- `robots.txt` (https://www.tvn-2.com/robots.txt) disallows only `/api/`, `/buscador/`, `/tag/`, and lists the sitemap index.
  Fetching article pages is allowed.
- Sitemap index (`data/raw/news/tvn/tvn_sitemap/index.xml`, https://www.tvn-2.com/tvn_sitemap_index.xml) lists monthly `contents_*`, `agencias_*`, `sections`, `tags`, `authors` and `google_news`.
- **Google News sitemap** (https://www.tvn-2.com/tvn_sitemap_google_news.xml) has an exact `news:publication_date`.
  It holds only 230 items spanning 2026-10-05 to 2026-10-07, so it is useless as a backfill.
  It is useful going forward (a daily snapshot gives exact publication dates for the live feed).
- RSS (https://www.tvn-2.com/rss/) has `pubDate` and `dcterms:modified` but only about 147 recent items.
- No AMP link and no `application/rss+xml` link in the sampled article.
- `/api/` is disallowed, so it was not touched.
- Prior work: `origin/prod:scripts/verificar_metadatos_tvn.py` reads `datePublished` from JSON-LD at 1 req/s; it only verified 171 topic candidates (`origin/prod:data/preparacion_tvn/README.md`).

### 4. Cost of fetching dates

- Observed: 260 pages in 10 min 50 s, about 2.5 s per page with a 1 s sleep and no concurrency.
- All 29,881 items: 8.3 h at exactly 1 req/s, about 21 h at the observed pace.
- Flagged outliers only (about 75): about 2 to 3 minutes.
- Only items later selected as topic candidates (like prod's 171): a few minutes.
- Risk of the full crawl: load on the source, the site terms forbid copying content (`docs/research/g1-data-sources.md`), long unattended run.
  Fetching metadata only is the same posture as prod's script.

## Options compared

| Option | Accuracy | Cost | Effort | Risk |
|---|---|---|---|---|
| A. `lastmod` as is | 100% within 1 day on random sample, about 0.15% of items wrong by days to years | 0 fetches | Minutes | Old items leak into the window and into recency U |
| B. Interpolate from id | Median 4 h, p90 13 h, 98% within 1 day | 0 fetches | Hours, needs anchors | Worse than A, fails on outliers |
| C. Fetch every page | Exact (JSON-LD plus meta fallback) | 8.3 h to 21 h | Medium, needs resume and retry | Load, politeness, terms, time |
| D. Hybrid: `lastmod` plus fetch flagged items | Exact for flagged, A elsewhere | About 75 fetches, about 3 min | Low | Tiny residual of unflagged old items |
| E. Google News sitemap snapshot | Exact | 1 fetch per day | Low | Only recent items, not a backfill |

## Suggested implementation

- Step `fecha_publicacion` reads only from `data/raw`: parse the monthly sitemaps, set `fecha_publicacion = lastmod` and keep `fecha_modificacion = lastmod` as a separate field (contract §7 in `docs/challenge/07-contrato-de-datos.md`).
- Flag suspicious items in that step: id more than 300 below the previous month's p99 id, or `lastmod` before the window start.
  About 75 items.
- Fetch only the flagged pages at 1 req/s with a descriptive User-Agent, resume support, and save the extracted metadata (`datePublished`, else `article:published_time`, plus `dateModified`) to `data/raw/news/tvn/page_dates/*.jsonl` with `_fetches.jsonl`-style provenance, no article bodies.
- Overwrite `fecha_publicacion` for flagged items with the fetched value, drop items now outside 2025-10-02 to 2026-10-07 (D-02), and add a column or flag such as `fecha_publicacion_fuente` (`sitemap_lastmod` or `pagina`) so tests T03 and T04 can report it.
- Optional: save a daily copy of the Google News sitemap and the RSS into `data/raw/news/tvn/` so live items carry exact dates.
- Optional: fetch the dates of the final topic candidates (as prod did) as a cheap second check on the items that drive the score.
