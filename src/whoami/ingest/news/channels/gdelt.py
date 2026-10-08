"""Resumable GDELT DOC captures. Detection time is never publication time."""

import json
import time
import urllib.error
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from whoami.contracts import news_window_start
from whoami.ingest import http
from whoami.ingest.http import Response
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import belongs_to_outlet, clean_text, parse_iso, section_of
from whoami.ingest.news.sources import Channel, Feed, Source
from whoami.ingest.raw import FETCH_LOG, RawStore

MAX_RECORDS = 250
ATTEMPTS = 5
MIN_SPACING_SECONDS = 6
BACKOFF_SECONDS = 30
MIN_SLICE = timedelta(minutes=1)
_last_request_at = float("-inf")


def fetch(feed: Feed, store: RawStore) -> None:
    """Newest day first; stop on exhausted retries so an outage costs one slice."""
    cutoff = datetime.now(UTC).replace(microsecond=0)
    start = news_window_start(cutoff)
    completed = {
        record["url"] for record in store.records(FETCH_LOG)
        if record.get("complete") and (store.directory / record["name"]).is_file()
    }
    end = cutoff
    while end >= start:
        day_start = max(start, end.replace(hour=0, minute=0, second=0))
        _fetch_slice(feed.url, store, day_start, end, completed)
        end = day_start - timedelta(seconds=1)


def _fetch_slice(endpoint: str, store: RawStore, start: datetime, end: datetime, completed: set[str]) -> None:
    url = endpoint + "?" + urlencode({
        "query": "sourcecountry:PM", "mode": "artlist", "format": "json",
        "maxrecords": MAX_RECORDS, "sort": "datedesc",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"), "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    })
    if url in completed:
        return
    articles = _capture(url, store)
    print(f"    GDELT {start.isoformat()} .. {end.isoformat()}: {len(articles)} items", flush=True)
    if len(articles) < MAX_RECORDS:
        completed.add(url)
        return
    if end - start < MIN_SLICE:
        raise RuntimeError("GDELT reached the 250-record cap in a one-minute slice; coverage is partial")
    middle = start + timedelta(seconds=int((end - start).total_seconds()) // 2)
    _fetch_slice(endpoint, store, middle + timedelta(seconds=1), end, completed)
    _fetch_slice(endpoint, store, start, middle, completed)


def _capture(url: str, store: RawStore) -> list[dict]:
    global _last_request_at
    for attempt in range(1, ATTEMPTS + 1):
        time.sleep(max(0, MIN_SPACING_SECONDS - (time.monotonic() - _last_request_at)))
        _last_request_at = time.monotonic()
        started = time.monotonic()
        status, body, headers, error = None, b"", {}, None
        try:
            response = http.get(url, attempts=1, timeout=60)
            status, body, headers = 200, response.body, response.headers
        except urllib.error.HTTPError as failure:
            status, body = failure.code, failure.read()
            headers = {key.lower(): value for key, value in failure.headers.items()}
            error = f"HTTP {status}"
        except (urllib.error.URLError, TimeoutError) as failure:
            error = f"{type(failure).__name__}: {failure}"
        articles = _articles(body) if status == 200 else None
        if status == 200 and articles is None:
            error = "Empty or invalid GDELT JSON response"
        name = f"capture_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid4().hex[:8]}.json"
        store.save(name, Response(url, body, headers), metadata={
            "status": status, "latency_seconds": round(time.monotonic() - started, 3),
            "bytes": len(body), "attempt": attempt, "error": error,
            "complete": articles is not None and len(articles) < MAX_RECORDS,
        })
        if articles is not None:
            return articles
        print(f"    GDELT attempt {attempt}/{ATTEMPTS}: {error}", flush=True)
        if status is not None and status not in http.RETRYABLE_STATUS and status != 200:
            break
        if attempt < ATTEMPTS:
            delay = BACKOFF_SECONDS * 2 ** (attempt - 1)
            try:
                delay = max(delay, float(headers.get("retry-after", 0)))
            except ValueError:
                pass
            time.sleep(delay)
    raise RuntimeError(f"GDELT capture failed: {error}; attempts saved in {store.directory}")


def _articles(body: bytes) -> list[dict] | None:
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
        return None
    if not all(isinstance(article, dict) for article in payload["articles"]):
        return None
    return payload["articles"]


def parse(source: Source, store: RawStore) -> Iterator[Article]:
    for file in store.files():
        for item in _articles(file.read()) or []:
            url = item.get("url")
            if not belongs_to_outlet(url, source.domain):
                continue
            yield Article(
                source=source.key, channel=Channel.GDELT_DOC, url=url,
                title=clean_text(item.get("title") if isinstance(item.get("title"), str) else None),
                fetched_at=file.fetched_at,
                detected_at=parse_iso(item.get("seendate") if isinstance(item.get("seendate"), str) else None),
                section=section_of(url),
            )


def coverage(store: RawStore) -> dict:
    """Successful intervals and errors, including captures with no article rows."""
    records = store.records(FETCH_LOG)
    completed = {record["url"] for record in records if record.get("complete")}
    return {
        "intentos": len(records), "consultas_completas": len(completed),
        "errores_por_estado": {
            str(status): sum(record.get("status") == status and bool(record.get("error")) for record in records)
            for status in sorted({record.get("status") for record in records}, key=str)
            if any(record.get("status") == status and record.get("error") for record in records)
        },
        "intervalos_completos": sorted(completed), "limite_por_consulta": MAX_RECORDS,
        "nota": "Cobertura de detección, no de publicación. Consultas con 250 filas requieren subdivisión.",
    }
