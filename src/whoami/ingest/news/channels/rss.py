"""RSS feeds. They only hold the latest items, so every fetch is kept as a new capture."""

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from whoami.contracts import PublicationDateOrigin
from whoami.ingest import http
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import clean_text, parse_rss_date, section_of
from whoami.ingest.news.sources import Channel, Feed, Source
from whoami.ingest.raw import RawStore, capture_name


def fetch(feed: Feed, store: RawStore) -> None:
    store.save(capture_name(), http.get(feed.url))


def parse(source: Source, store: RawStore) -> Iterator[Article]:
    for file in store.files():
        for item in ET.fromstring(file.read()).iter("item"):
            url = (item.findtext("link") or "").strip()
            if not url:
                continue
            yield Article(
                source=source.key,
                channel=Channel.RSS,
                url=url,
                title=clean_text(item.findtext("title")),
                fetched_at=file.fetched_at,
                published_at=parse_rss_date(item.findtext("pubDate")),
                published_at_origin=PublicationDateOrigin.FEED,
                description=clean_text(item.findtext("description")),
                section=section_of(url),
            )
