"""WordPress REST API of official bodies: press releases with `date_gmt`, excerpt and categories.

Each fetch replaces the previous pull, since it always covers the whole window.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from whoami.contracts import PublicationDateOrigin, news_window_start
from whoami.ingest import http
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import clean_text, parse_iso
from whoami.ingest.news.sources import Channel, Feed, Source
from whoami.ingest.raw import RawStore

PAGE_SIZE = 100
POST_FIELDS = "id,link,title,excerpt,date_gmt,categories"
POSTS_PREFIX = "posts_p"
CATEGORIES_PREFIX = "categories_p"
#: `after` compares the site's local time; the window filter in build does the exact cut.
AFTER_MARGIN = timedelta(days=1)


def fetch(feed: Feed, store: RawStore) -> None:
    after = (news_window_start(datetime.now(UTC)) - AFTER_MARGIN).strftime("%Y-%m-%dT%H:%M:%S")
    store.delete(POSTS_PREFIX)
    store.delete(CATEGORIES_PREFIX)
    _fetch_pages(store, POSTS_PREFIX, f"{feed.url}/wp-json/wp/v2/posts?after={after}&_fields={POST_FIELDS}")
    _fetch_pages(store, CATEGORIES_PREFIX, f"{feed.url}/wp-json/wp/v2/categories?_fields=id,name")


def parse(source: Source, store: RawStore) -> Iterator[Article]:
    files = store.files()
    categories = {
        category["id"]: clean_text(category["name"])
        for file in files
        if file.name.startswith(CATEGORIES_PREFIX)
        for category in json.loads(file.read())
    }
    for file in files:
        if not file.name.startswith(POSTS_PREFIX):
            continue
        for post in json.loads(file.read()):
            url = (post.get("link") or "").strip()
            if not url:
                continue
            names = [categories.get(category_id) for category_id in post.get("categories") or []]
            yield Article(
                source=source.key,
                channel=Channel.WP_API,
                url=url,
                title=clean_text((post.get("title") or {}).get("rendered")),
                fetched_at=file.fetched_at,
                published_at=parse_iso(post.get("date_gmt")),
                published_at_origin=PublicationDateOrigin.FEED,
                description=clean_text((post.get("excerpt") or {}).get("rendered")),
                section=", ".join(name for name in names if name) or None,
            )


def _fetch_pages(store: RawStore, prefix: str, url: str) -> None:
    page, total_pages = 1, 1
    while page <= total_pages:
        response = http.get(f"{url}&per_page={PAGE_SIZE}&page={page}")
        store.save(f"{prefix}{page:03d}.json", response)
        total_pages = int(response.headers.get("x-wp-totalpages", 1))
        page += 1
