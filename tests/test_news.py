import json
import pytest
from datetime import UTC, datetime

from whoami.contracts import PublicationDateOrigin
from whoami.ingest.http import Response
from whoami.ingest.news.article import Article
from whoami.ingest.news.build import merge
from whoami.ingest.news.channels import tvn_sitemap, wp_api
from whoami.ingest.news.sources import SOURCES, Channel
from whoami.ingest.raw import RawStore

TVN = next(source for source in SOURCES if source.key == "tvn")
MEF = next(source for source in SOURCES if source.key == "mef")
URL = "https://www.tvn-2.com/nacionales/canal-restringe-transitos_1_2264701.html"


def article(channel: Channel, **fields) -> Article:
    defaults = {"source": "tvn", "url": URL, "title": "Canal restringe tránsitos", "fetched_at": datetime(2026, 10, 7, tzinfo=UTC)}
    return Article(channel=channel, **(defaults | fields))


def test_failed_wordpress_refresh_preserves_the_previous_snapshot(tmp_path, monkeypatch):
    from whoami.ingest.news.sources import Feed
    store = RawStore(tmp_path)
    store.save("posts_p001.json", Response("https://x.invalid", b'[]', {}))
    store.save("categories_p001.json", Response("https://x.invalid", b'[]', {}))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    def fail(url):
        raise TimeoutError("test")
    monkeypatch.setattr(wp_api.http, "get", fail)
    with pytest.raises(TimeoutError):
        wp_api.fetch(MEF.feeds[0], store)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("url", ["not-a-url", "javascript:alert(1)", "https://", "https://x.invalid:bad/", "https://a b.test/"])
def test_malformed_urls_are_reported_as_exclusions(url):
    from whoami.ingest.news.build import exclusion
    stamp = datetime(2026, 10, 7, tzinfo=UTC)
    [item] = merge([article(Channel.RSS, url=url, published_at=stamp, published_at_origin=PublicationDateOrigin.FEED)])
    reason = exclusion(item, stamp)
    assert reason is not None and reason.value == "url_invalida"


def test_feed_date_wins_over_page_and_lastmod():
    lastmod = datetime(2026, 10, 6, 12, tzinfo=UTC)
    feed_date = datetime(2026, 10, 6, 10, tzinfo=UTC)
    [item] = merge([
        article(Channel.TVN_SITEMAP, modified_at=lastmod),
        article(Channel.RSS, url=URL.replace("www.", ""), published_at=feed_date, published_at_origin=PublicationDateOrigin.FEED),
    ])

    assert item.published_at == feed_date
    assert item.published_at_origin == PublicationDateOrigin.FEED
    assert item.modified_at == lastmod


def test_lastmod_is_the_fallback_publication_date():
    lastmod = datetime(2026, 10, 6, 12, tzinfo=UTC)
    [item] = merge([article(Channel.TVN_SITEMAP, modified_at=lastmod)])

    assert item.published_at == lastmod
    assert item.published_at_origin == PublicationDateOrigin.LASTMOD


def test_page_date_prefers_json_ld_and_falls_back_to_meta():
    json_ld = '<script type="application/ld+json">{"datePublished":"2025-06-01T10:00:00-05:00"}</script>'
    meta_only = '<meta content="2025-07-30T08:00:00Z" property="article:published_time">'

    assert tvn_sitemap.extract_published_date(json_ld) == datetime(2025, 6, 1, 15, tzinfo=UTC)
    assert tvn_sitemap.extract_published_date(meta_only) == datetime(2025, 7, 30, 8, tzinfo=UTC)
    assert tvn_sitemap.extract_published_date("<html></html>") is None


def test_wp_api_maps_posts_with_category_names(tmp_path):
    store = RawStore(tmp_path)
    post = {
        "link": "https://www.mef.gob.pa/2026/10/deuda/",
        "title": {"rendered": "MEF informa sobre la deuda &#8211; septiembre"},
        "excerpt": {"rendered": "<p>El saldo de la deuda pública&nbsp;cerró en...</p>"},
        "date_gmt": "2026-10-06T15:00:00",
        "categories": [7],
    }
    store.save("posts_p001.json", Response("https://www.mef.gob.pa/wp-json/wp/v2/posts", json.dumps([post]).encode(), {}))
    store.save("categories_p001.json", Response("https://www.mef.gob.pa/wp-json/wp/v2/categories", b'[{"id": 7, "name": "Comunicados"}]', {}))

    [item] = wp_api.parse(MEF, store)

    assert item.title == "MEF informa sobre la deuda – septiembre"
    assert item.description == "El saldo de la deuda pública cerró en..."
    assert item.published_at == datetime(2026, 10, 6, 15, tzinfo=UTC)
    assert item.published_at_origin == PublicationDateOrigin.FEED
    assert item.section == "Comunicados"
