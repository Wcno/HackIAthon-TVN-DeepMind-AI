# GDELT DOC 2.0 - why it fails and what to do

Research date: 2026-10-06 (UTC 2026-10-07).
Scope: multi-outlet Panama news for the last 30 days (decision D-04).
Evidence tags: `branch:path` = repo file, URL = external source, "live" = test run from this machine (section 3).

## 1. TL;DR - ranked recommendation

1. **Keep GDELT DOC as a patient, low-rate channel, with a 60 s timeout and retry on 429.**
   One query `Panama sourcecountry:PM`, `timespan=30d`, `maxrecords=250` returned 250 articles from 8 Panamanian outlets in 15.4 s (live).
   The earlier "timeouts" were our 10 s client timeout: even a successful call takes about 15 s.
2. **Freeze the first good pull into `data/raw/news/gdelt/doc/` and never depend on a live call again.**
   The window is rolling, so the pull must happen before the demo, and the saved file is the evidence.
3. **Add 2-3 outlet news sitemaps/RSS as the reliable second channel** (La Prensa, Telemetro, La Estrella, Panama America).
   They cover only about 2 days each, so capture daily (cron or manual) until the deadline.
4. **Use GDELT GKG raw files only as a fallback** (public, stable, 15-min files, but a thin Panama sample).
5. **Skip BigQuery, Google News RSS and paid news APIs** for the MVP (setup cost or poor outlet coverage).

Key finding: the API is not "down".
It is throttled and slow, and the 429 text asks for one request every 5 s, but spacing requests more than 5 s did not prevent 429s (8 of 9 calls, section 3).
Treat success as a lottery with a long timeout, not as a rate you can tune.

## 2. Why it fails (evidence)

| Symptom | Evidence | Likely cause |
|---|---|---|
| HTTP 429 | Body text: "Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries. All high-traffic users should switch to our ngrams dataset" (live; same text quoted in `origin/NoSkill:src/senal/ingest/_crudo.py`) | Server-side throttle by GDELT. Limit is not documented in the official DOC post (https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) |
| 429 even with 7-8 s between calls | 11 of 12 spaced calls were 429, each taking 11-14 s to answer (live) | Inference: the throttle is probably shared (global or per-IP load across all users), not only our own rate. Not documented |
| Read timeout | `origin/prod:data/preparacion_tvn/resumen.json`: 4 errors "Read timed out (read timeout=10)". A successful call took 15.4 s and 429s took 11-14 s (live) | Our 10 s timeout is below normal latency. Use 60 s |
| Empty answer | `origin/prod:data/preparacion_tvn/README.md` reports 1 empty answer | Not reproduced. Known behaviour: a query with no matches returns an empty body, not `{"articles": []}` (inference, not confirmed in a primary source). Guard `json.loads` |
| Nothing older than 3 months | "rolling window of the last 3 months", and `startdatetime/enddatetime` must fall inside it (https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | By design. D-04 (30 days) fits. The old 2025-10 to 2026-09 plan does not |
| Max 250 per query | `maxrecords` default 75, max 250 (same post) | By design. Split by date or by query and dedupe by URL |

Not found despite searching: any GDELT announcement of a 2025-2026 outage, IP block or User-Agent requirement.
Only a March 2025 SSL certificate expiry on api.gdeltproject.org was mentioned in the r/gdelt feed (https://lr.in.psf.lt/r/gdelt), not verified at the source.
Query syntax: `sourcecountry:` accepts a country name or a FIPS code, and `sourcelang:` a language code (same blog post).
`sourcecountry:PM` worked.
The docs do not state a minimum keyword length.
Note that GDELT FIPS "PM" means Panama.

## 3. Live tests

Setup: Python `urllib`, User-Agent `hackathon-research/0.1 (<contact>; low-rate test)`, timeout 60 s, 7-8 s sleep between calls, 12 DOC calls total.
Script and raw outputs: `/tmp/claude-1000/-home-jwhoami-Development-projects-hackathons-hackiaton-whoamisfc/38b564ac-1893-4a58-9ed7-48df613c72dc/scratchpad/` (`gdelt_test.py`, `t2.py`, `t*.out`, `u*.out`).
All use `mode=artlist&format=json`.

| # | Query | Window | maxrecords | Status | Latency | Items |
|---|---|---|---|---|---|---|
| t1 | `Panama` | timespan 1d | 50 | 429 | 14.0 s | - |
| t2 | `Panama sourcecountry:PM` | 1d | 50 | 429 | 12.1 s | - |
| t3 | `sourcecountry:PM` | 7d | 250 | 429 | 12.2 s | - |
| t4 | `"Canal de Panamá" sourcelang:spanish` | 7d | 250 | 429 | 11.3 s | - |
| t5 | `"Panama Canal"` | 7d | 250 | 429 | 11.0 s | - |
| t6 | `domain:tvn-2.com` | 30d | 250 | 429 | 12.0 s | - |
| t7 | `Panama sourcecountry:PM` | start/end 2 days | 250 | 429 | 12.9 s | - |
| **t8** | **`Panama sourcecountry:PM`** | **30d** | **250** | **200** | **15.4 s** | **250** |
| t9 | `panama` | 3h | 50 | 429 | 12.5 s | - |
| u1 | `sourcecountry:PM` | start/end 1 day | 250 | 429 | 11.2 s | - |
| u2 | `sourcecountry:PM`, `sort=datedesc` | start/end 1 day | 250 | 429 | 11.8 s | - |
| u3 | `"Canal de Panamá" sourcecountry:PM` | 30d | 250 | 429 | 11.5 s | - |
| u4 | `data.gdeltproject.org/gdeltv2/lastupdate.txt` (static file, not DOC) | - | - | 200 | 0.5 s | 3 file URLs |

Result of t8 (the only success):

- 250 unique URLs, all `language=Spanish`, all `sourcecountry=Panama`, `seendate` from 2026-09-07 to 2026-10-02.
- 8 domains: prensa.com 52, laestrella.com.pa 47, telemetro.com 46, midiario.com 30, critica.com.pa 28, panamaamerica.com.pa 28, diaadia.com.pa 15, rpctv.com 4.
- TVN (`tvn-2.com`) did not appear in the top 250, and the date range shows the cap truncates a 30-day query, so slicing by day is needed (not verified live because of the 429s).
- Fields per item: `url`, `url_mobile`, `title`, `seendate`, `socialimage`, `domain`, `language`, `sourcecountry`. There is no publication date, so `seendate` goes to `fecha_deteccion` (`docs/challenge/07-contrato-de-datos.md`).

Conclusions: query variants and window style (`timespan` vs `startdatetime`) did not change the outcome, the 429 pattern was the same for all.
Short or lowercase keywords did not produce a different error, only the same 429.
The 429 itself takes 11-14 s to arrive, so a naive 10 s timeout fails before any answer.

## 4. Alternatives and options

GKG raw check (live): `https://data.gdeltproject.org/gdeltv2/lastupdate.txt` answered in 0.5 s.
`<timestamp>.gkg.csv.zip` files are about 2.4 MB and 420-810 records each, with the article URL in the 5th column and the outlet domain in the 4th.
Sampling 20 of the 96 files of 2026-09-20: 5 records from Panamanian domains, all `newsroompanama.com`, none from prensa.com or telemetro.com.
Every download took about 1 s (HTTP 200, no throttling seen).
The master list (https://data.gdeltproject.org/gdeltv2/masterfilelist.txt, 128 MB) exists but is not needed, file names are `YYYYMMDDHHMMSS`.
The GKG file seems to be a thin sample for Panama, compared to the DOC index. The sample is small, so treat this as a rough estimate.

| Option | Panama coverage | Effort | Cost | Reliability | Terms |
|---|---|---|---|---|---|
| GDELT DOC, `sourcecountry:PM`, 30d | Good: 8 Panamanian outlets in one call (live) | Low (one function, long timeout, retry) | Free | Poor: 11 of 12 calls got 429 | Data free and open, attribution to GDELT with a link required (https://www.gdeltproject.org/about.html). Does not grant media rights (`docs/challenge/06-datos-publicos.md`) |
| GDELT GKG/Events raw 15-min files | Weak in our sample (1 outlet in 20 files) | Medium: ~2,880 files for 30 days (~7 GB), filter by domain | Free | Good: static files, 0.5-1 s | Same as above (https://www.gdeltproject.org/about.html) |
| GDELT on BigQuery (`gdelt-bq.gdeltv2.gkg`) | Same as GKG, but SQL | Medium: Google Cloud project, partitioned table filter | Free tier allows a monthly query allowance and 10 GiB storage (https://cloud.google.com/bigquery/pricing); the exact TiB figure was not visible when fetched. GKG is 3.6 TB, so use the partitioned table and a date filter (https://blog.gdeltproject.org/announcing-partitioned-gdelt-bigquery-tables/) | Good | Needs a Google account and billing or sandbox (sandbox: no billing account, 60-day expiry, per the same pricing page). Extra setup for a hackathon |
| Outlet news sitemaps and RSS (prensa.com, telemetro.com, laestrella.com.pa, panamaamerica.com.pa) | Direct, real `pubDate`. prensa.com RSS returned 100 items (live). Telemetro `/rss` is 404, use its news sitemap | Low (code exists in `origin/NoSkill:src/senal/ingest/medios.py`) | Free | Good, but only about 2 days of history per `docs/research/g1-data-sources.md` | No reuse terms found, keep metadata only. prensa.com robots.txt allows crawling except `/buscador/*` and similar (https://www.prensa.com/robots.txt) |
| Google News RSS (`news.google.com/rss/search?q=Panamá+when:30d&gl=PA`) | Poor: 100 items, top sources were Infobae 27, Vietnam.vn 9, Prensa Latina 6 (live). Links are `news.google.com/rss/articles/...` redirects, not outlet URLs | Low | Free | Unofficial, can change or block | Unofficial feed, no stated terms. Not recommended |
| Common Crawl CC-NEWS | Global, WARC files on S3, daily (https://commoncrawl.org/blog/news-dataset-available) | High: WARC parsing, large | AWS transfer costs | Good | Common Crawl terms, copyrighted content |
| Media Cloud API | Unknown for Panama, page did not state coverage, limits or price (https://www.mediacloud.org/documentation/search-api-guide) | Medium | Unknown | Unknown | Unverified. Not recommended without a test |
| GNews API free plan | Sources from 80,000 outlets, country and language filters (https://docs.gnews.io/); free-plan limits not verified | Low | Free tier, limits unverified | Unknown | Check commercial terms first. Not recommended |

## 5. Suggested implementation

Fits our design: an ingest channel saves untouched responses with a fetch log, then an offline build step normalizes them.

- **Channel `gdelt/doc` writes to `data/raw/news/gdelt/doc/`.**
  Save each response body byte for byte, with a name like `panama_pm_2026-10-07T0412Z.json`, and one line per attempt in a `fetch_log.jsonl` (UTC time, URL, status, latency, bytes, SHA-256, error).
  Failed attempts (429, timeout, empty body) are logged and the body is saved too.
- **Fetcher rules:** User-Agent with a contact, timeout 60 s, at least 6 s between calls, on 429 wait 30-60 s with growing backoff, at most 5 attempts per query, then stop and log.
  Treat an empty body as "no data", not as a crash.
- **Query plan:** `Panama sourcecountry:PM` plus thematic variants (logistics, tourism, economy, natural events, in Spanish), sliced by day with `startdatetime/enddatetime` inside the last 30 days, `maxrecords=250`.
  Run it once, slowly, in the background, and commit nothing but the raw files you keep.
  Stop as soon as there are at least 2 outlets covering the same story for the demo case.
- **Second channel `sitemaps/<outlet>` writes to `data/raw/news/<outlet>/sitemap/`.**
  Reuse `medios.py` from `origin/NoSkill`, run daily until the deadline so the window grows.
  This channel is the safety net if GDELT keeps answering 429.
- **Offline build step:** read raw files only, dedupe by URL (strip query strings), map `seendate` to `fecha_deteccion`, leave `fecha_publicacion` empty for GDELT rows (or fill it from the outlet's own date), and tag each row with its source channel.
- **Fallback:** if there is no good DOC pull by the deadline, parse a day of GKG files (`gkg.csv.zip`) filtered by Panamanian domains, and state on the coverage panel that GDELT was partial.
  Record in the ADR or `docs/challenge/00-decisiones-del-equipo.md` that the 30-day window follows from the DOC 3-month limit.

## 6. Open questions

- Is the 429 tied to our IP or to global load? Test again from another network or at a different hour, and compare.
- Do day-sliced queries also hit the 250 cap? Not verified, because the calls were throttled.
- Is TVN indexed by GDELT? It was absent from the top 250, and `domain:tvn-2.com` returned 429 (untested).

## 7. Integration check from the Windows checkout (2026-10-07 Panama / 2026-10-08 UTC)

The provided handoff was used as diagnostic context. Physical network type and
whether this public IP differs from the original machine are unknown; these
results cannot settle per-IP versus global throttling.

The standalone one-day DOC probe returned 429 in 11.159 s, 444 bytes. The ingest
then retained the following attempts in `data/raw/news/gdelt/doc/_fetches.jsonl`:

| UTC capture time | Status | Seconds | Bytes | Attempt |
| --- | --- | --- | --- | --- |
| 00:43:21 | 429 | 11.706 | 444 | 1 |
| 00:43:29 | 429 | 10.755 | 444 | 1, separate run interrupted |
| 00:44:01 | 429 | 10.818 | 444 | 2 |
| 00:45:15 | 429 | 13.455 | 444 | 3 |
| 00:47:27 | 429 | 12.442 | 444 | 4 |
| 00:51:38 | 429 | 10.432 | 444 | 5 |

DOC ingestion stops after that failed slice. No successful DOC interval is
claimed. The failed raw responses remain evidence, and offline parsing skips
them. No second physical network was tested.

**GKG multilingual fallback works.** `lastupdate-translation.txt` returned 200.
Six hourly `translation.gkg.csv.zip` batches from 18:00–23:00 UTC on October 7
were downloaded with HTTP 200, each in 2.2–4.8 seconds during the final ingest.
The archives contain 41 articles from five registered Panamanian outlets with
headlines in `PAGE_TITLE`. The earlier English-only GKG sample did not measure
this multilingual stream. The format is documented by the
[official GKG 2.1 codebook](https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf).

Implementation: `src/whoami/ingest/news/channels/{gdelt,gdelt_gkg}.py`.
This is a partial hourly sample, not continuous coverage of the 30-day window.
Capture direct outlet feeds with `--only prensa,telemetro,panamaamerica`, GKG
with `--only gdelt-gkg`, and retry DOC independently with `--only gdelt`.
Coverage, rights, demonstration URLs and reproducibility are recorded in
`docs/g1-completion.md` and `data/processed/calidad_noticias.json`.
