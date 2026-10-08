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


@pytest.mark.parametrize("failure_at", [2, 3])
def test_later_wordpress_failure_keeps_posts_categories_and_fetch_log(tmp_path, monkeypatch, failure_at):
    store = RawStore(tmp_path / "wordpress")
    store.save("posts_p001.json", Response("https://x.invalid", b'[{"id": 1}]', {}))
    store.save("categories_p001.json", Response("https://x.invalid", b'[{"id": 7}]', {}))
    before = {p.name: p.read_bytes() for p in store.directory.iterdir()}
    calls = []
    def download(url):
        calls.append(url)
        if len(calls) == failure_at:
            raise TimeoutError("Later page unavailable")
        return Response(url, b'[]', {"x-wp-totalpages": "2" if "posts?" in url else "1"})
    monkeypatch.setattr(wp_api.http, "get", download)
    with pytest.raises(TimeoutError):
        wp_api.fetch(MEF.feeds[0], store)
    assert len(calls) == failure_at
    assert {p.name: p.read_bytes() for p in store.directory.iterdir()} == before


def test_successful_wordpress_refresh_replaces_all_pages_and_remains_parseable(tmp_path, monkeypatch):
    store = RawStore(tmp_path / "wordpress")
    store.save("posts_p002.json", Response("https://x.invalid", b'[{"id": 1}]', {}))
    store.save("categories_p002.json", Response("https://x.invalid", b'[{"id": 7}]', {}))
    new_post = {"link": "https://www.mef.gob.pa/2026/10/nuevo/", "title": {"rendered": "Nueva noticia"},
                "date_gmt": "2026-10-07T12:00:00", "categories": [9]}
    def download(url):
        rows = [new_post] if "posts?" in url else [{"id": 9, "name": "Nuevos comunicados"}]
        return Response(url, json.dumps(rows).encode(), {"x-wp-totalpages": "1"})
    monkeypatch.setattr(wp_api.http, "get", download)
    wp_api.fetch(MEF.feeds[0], store)
    [parsed] = wp_api.parse(MEF, store)
    assert parsed.title == "Nueva noticia" and parsed.section == "Nuevos comunicados"
    assert not (store.directory / "posts_p002.json").exists()
    assert not (store.directory / "categories_p002.json").exists()


@pytest.mark.parametrize("url", ["not-a-url", "javascript:alert(1)", "https://", "https://x.invalid:bad/", "https://a b.test/", "https://[broken/path"])
def test_malformed_urls_are_reported_as_exclusions(url):
    from whoami.ingest.news.build import exclusion
    stamp = datetime(2026, 10, 7, tzinfo=UTC)
    [item] = merge([article(Channel.RSS, url=url, published_at=stamp, published_at_origin=PublicationDateOrigin.FEED)])
    reason = exclusion(item, stamp)
    assert reason is not None and reason.value == "url_invalida"


@pytest.mark.parametrize("channel", [Channel.RSS, Channel.TVN_SITEMAP, Channel.WP_API])
@pytest.mark.parametrize("url, valid", [("https://[broken/path", False), ("http://example.test/news/item", True), ("https://example.test/news/item", True)])
def test_channel_parsing_and_build_account_for_invalid_urls(tmp_path, monkeypatch, channel, url, valid):
    from whoami.ingest.news.channels import rss
    from whoami.ingest.news import build as news_build
    store = RawStore(tmp_path / "raw")
    if channel == Channel.RSS:
        raw = f'<rss><channel><item><link>{url}</link><title>Noticia válida</title><pubDate>Wed, 07 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        store.save("rss.xml", Response("https://example.test", raw.encode(), {}))
        parsed = list(rss.parse(TVN, store))
    elif channel == Channel.TVN_SITEMAP:
        raw = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"><url><loc>{url}</loc><lastmod>2026-10-07T12:00:00Z</lastmod><image:image><image:title>Noticia válida</image:title></image:image></url></urlset>'
        store.save("contents_2026_10.xml", Response("https://example.test", raw.encode(), {}))
        parsed = list(tvn_sitemap.parse(TVN, store))
    else:
        raw = [{"link": url, "title": {"rendered": "Noticia válida"}, "date_gmt": "2026-10-07T12:00:00"}]
        store.save("posts_p001.json", Response("https://example.test", json.dumps(raw).encode(), {}))
        parsed = list(wp_api.parse(MEF, store))
    assert len(parsed) == 1
    monkeypatch.setattr(news_build.channels, "parse", lambda source, feed: parsed if source.key == parsed[0].source else [])
    monkeypatch.setattr(news_build, "PROCESSED", tmp_path / "processed")
    for name in ("NEWS_CSV", "EXCLUDED_NEWS_CSV", "SOURCES_JSON", "NEWS_QUALITY_JSON"):
        monkeypatch.setattr(news_build, name, tmp_path / "processed" / name.lower())
    report = news_build.build()
    if valid:
        assert report["incluidas"] == 1
        assert not report["excluidas_por_motivo"].get("url_invalida")
    else:
        assert report["incluidas"] == 0
        assert report["excluidas_por_motivo"]["url_invalida"] == 1


def test_invalid_scheme_cannot_hide_a_later_legitimate_http_article():
    from whoami.ingest.news.build import exclusion
    stamp = datetime(2026, 10, 7, tzinfo=UTC)
    common = {"published_at": stamp, "published_at_origin": PublicationDateOrigin.FEED}
    items = merge([article(Channel.RSS, url="ftp://example.test/news/item", **common),
                   article(Channel.RSS, url="https://example.test/news/item", **common)])
    retained = [item for item in items if exclusion(item, stamp) is None]
    assert len(retained) == 1 and retained[0].url == "https://example.test/news/item"


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
