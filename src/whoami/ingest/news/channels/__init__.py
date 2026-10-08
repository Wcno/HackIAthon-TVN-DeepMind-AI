"""One module per channel: `fetch` downloads to raw, `parse` turns raw into articles offline."""

from collections.abc import Iterator
from types import ModuleType

from whoami.ingest.news.article import Article
from whoami.ingest.news.channels import gdelt, gdelt_gkg, news_sitemap, rss, tvn_sitemap, wp_api
from whoami.ingest.news.sources import Channel, Feed, Source

_MODULES: dict[Channel, ModuleType] = {
    Channel.TVN_SITEMAP: tvn_sitemap,
    Channel.RSS: rss,
    Channel.WP_API: wp_api,
    Channel.NEWS_SITEMAP: news_sitemap,
    Channel.GDELT_DOC: gdelt,
    Channel.GDELT_GKG: gdelt_gkg,
}


def fetch(source: Source, feed: Feed) -> None:
    _MODULES[feed.channel].fetch(feed, source.store(feed))


def parse(source: Source, feed: Feed) -> Iterator[Article]:
    return _MODULES[feed.channel].parse(source, source.store(feed))
