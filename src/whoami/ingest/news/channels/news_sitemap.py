"""Daily captures of outlet news sitemaps, with actual publication dates."""

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from whoami.contracts import PublicationDateOrigin
from whoami.ingest import http
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import clean_text, parse_iso, section_of
from whoami.ingest.news.sources import Channel, Feed, Source
from whoami.ingest.raw import RawStore, capture_name

NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}


def fetch(feed: Feed, store: RawStore) -> None:
    store.save(capture_name(), http.get(feed.url))


def parse(source: Source, store: RawStore) -> Iterator[Article]:
    for file in store.files():
        for entry in ET.fromstring(file.read()).findall("sm:url", NS):
            url = (entry.findtext("sm:loc", namespaces=NS) or "").strip()
            if not url:
                continue
            yield Article(
                source=source.key, channel=Channel.NEWS_SITEMAP, url=url,
                title=clean_text(entry.findtext("news:news/news:title", namespaces=NS)),
                fetched_at=file.fetched_at,
                published_at=parse_iso(entry.findtext("news:news/news:publication_date", namespaces=NS)),
                published_at_origin=PublicationDateOrigin.FEED,
                section=section_of(url),
            )
