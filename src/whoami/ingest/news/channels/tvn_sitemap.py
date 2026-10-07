"""TVN monthly sitemaps, the only TVN channel with history.

The index lists `tvn_sitemap_contents_YYYY_MM.xml`. Each entry has the URL, the
headline in `image:title` and `lastmod`, but no publication date. `lastmod` is
the publication time for almost every item; the exception is old articles that
were edited later, which are spotted by their URL id and dated from their page.
Evidence: docs/research/tvn-fecha-publicacion.md.
"""

import hashlib
import re
import statistics
import urllib.error
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from whoami.contracts import PublicationDateOrigin, news_window_start
from whoami.ingest import http
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import clean_text, parse_iso, section_of
from whoami.ingest.news.sources import Channel, Feed, Source
from whoami.ingest.raw import RawFile, RawStore

NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}
MONTH_FILE_PREFIX = "contents_"
#: Only the extracted dates are kept: the site terms forbid copying page content.
PAGE_DATES = "page_dates.jsonl"
#: An id this far below the previous month's 99th percentile belongs to an older article.
OUTLIER_ID_MARGIN = 300

_MONTH_IN_INDEX = re.compile(r"tvn_sitemap_contents_(\d{4}_\d{2})\.xml")
_ARTICLE_ID = re.compile(r"_(\d+)\.html$")
_JSON_LD_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_CONTENT = re.compile(r'content="([^"]+)"')


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    title: str | None
    lastmod: datetime | None

    @property
    def article_id(self) -> int | None:
        match = _ARTICLE_ID.search(self.url)
        return int(match.group(1)) if match else None


def fetch(feed: Feed, store: RawStore) -> None:
    now = datetime.now(UTC)
    index = http.get(feed.url)
    store.save("index.xml", index)
    published_months = set(_MONTH_IN_INDEX.findall(index.body.decode("utf-8", "replace")))
    month_before_window = news_window_start(now).replace(day=1) - timedelta(days=1)
    for month in months_between(month_before_window, now):
        if month in published_months:
            response = http.get(f"https://www.tvn-2.com/tvn_sitemap_contents_{month}.xml")
            store.save(f"{MONTH_FILE_PREFIX}{month}.xml", response)
    _fetch_page_dates(store, news_window_start(now))


def parse(source: Source, store: RawStore) -> Iterator[Article]:
    page_dates = {
        record["url"]: datetime.fromisoformat(record["date_published"])
        for record in store.records(PAGE_DATES)
        if record["date_published"]
    }
    for file in _month_files(store.files()):
        for entry in _entries(file):
            page_date = page_dates.get(entry.url)
            yield Article(
                source=source.key,
                channel=Channel.TVN_SITEMAP,
                url=entry.url,
                title=entry.title,
                fetched_at=file.fetched_at,
                published_at=page_date,
                published_at_origin=PublicationDateOrigin.PAGE if page_date else None,
                modified_at=entry.lastmod,
                section=section_of(entry.url),
            )


def outliers(files: list[RawFile], window_start: datetime) -> list[SitemapEntry]:
    """Entries in the window whose id is far below the previous month's ids."""
    entries_by_month = {file.name: list(_entries(file)) for file in _month_files(files)}
    months = sorted(entries_by_month)
    flagged = []
    for previous, current in zip(months, months[1:]):
        previous_ids = [entry.article_id for entry in entries_by_month[previous] if entry.article_id]
        if len(previous_ids) < 100:
            continue
        threshold = statistics.quantiles(previous_ids, n=100)[98] - OUTLIER_ID_MARGIN
        flagged += [
            entry
            for entry in entries_by_month[current]
            if entry.article_id and entry.article_id < threshold and entry.lastmod and entry.lastmod >= window_start
        ]
    return flagged


def extract_published_date(page: str) -> datetime | None:
    """JSON-LD `datePublished`, else `article:published_time` (videos and some sections lack the former)."""
    match = _JSON_LD_PUBLISHED.search(page)
    if match:
        return parse_iso(match.group(1))
    for tag in _META_TAG.findall(page):
        if 'property="article:published_time"' in tag and (content := _META_CONTENT.search(tag)):
            return parse_iso(content.group(1))
    return None


def months_between(start: datetime, end: datetime) -> list[str]:
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year}_{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _fetch_page_dates(store: RawStore, window_start: datetime) -> None:
    """Resumable: pages already dated are skipped, failed ones are retried on the next run."""
    already_dated = {record["url"] for record in store.records(PAGE_DATES)}
    pending = [entry for entry in outliers(store.files(), window_start) if entry.url not in already_dated]
    print(f"    {len(pending)} outlier pages to date")
    for entry in pending:
        try:
            response = http.get(entry.url)
        except urllib.error.URLError as error:
            print(f"    skipped {entry.url}: {error}")
            continue
        published = extract_published_date(response.body.decode("utf-8", "replace"))
        store.append_record(PAGE_DATES, {
            "url": entry.url,
            "sha256": hashlib.sha256(response.body).hexdigest(),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "date_published": published.isoformat() if published else None,
        })


def _month_files(files: list[RawFile]) -> list[RawFile]:
    return [file for file in files if file.name.startswith(MONTH_FILE_PREFIX)]


def _entries(file: RawFile) -> Iterator[SitemapEntry]:
    for entry in ET.fromstring(file.read()).findall("sm:url", NS):
        url = (entry.findtext("sm:loc", namespaces=NS) or "").strip()
        if url:
            yield SitemapEntry(
                url=url,
                title=clean_text(entry.findtext("image:image/image:title", namespaces=NS)),
                lastmod=parse_iso(entry.findtext("sm:lastmod", namespaces=NS)),
            )
