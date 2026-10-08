import hashlib
import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from whoami.contracts import PublicationDateOrigin
from whoami.ingest.http import Response
from whoami.ingest.output import write_json
from whoami.ingest.news import build, channels, ingest
from whoami.ingest.news.article import Article
from whoami.ingest.news.channels import gdelt, news_sitemap
from whoami.ingest.news.sources import GDELT_FEED, SOURCES, Channel
from whoami.ingest.raw import FETCH_LOG, RawStore

PR = next(source for source in SOURCES if source.key == "prensa")
NOW = datetime(2026, 10, 7, 18, tzinfo=UTC)
URL = "https://www.prensa.com/economia/canal/"


def payload(**fields):
    return json.dumps({"articles": [{"url": URL, "title": "Canal &amp; tránsitos", "seendate": "20261006T120000Z", **fields}]}).encode()


def test_gdelt_detection_is_kept_without_inventing_publication(tmp_path):
    store = RawStore(tmp_path)
    store.save("capture.json", Response("https://gdelt.test", payload(), {}))
    [article] = gdelt.parse(PR, store)
    [item] = build.merge([article])
    row = build._news_row(item)
    assert article.title == "Canal & tránsitos"
    assert article.detected_at == datetime(2026, 10, 6, 12, tzinfo=UTC)
    assert build.exclusion(item, NOW) is None
    assert row["fecha_publicacion"] == ""
    assert row["origen_fecha_publicacion"] == ""
    assert row["fecha_deteccion"] == "2026-10-06T12:00:00Z"
    assert row["medio"] == "La Prensa"


def test_detection_does_not_rescue_old_publication():
    [item] = build.merge([
        Article("prensa", Channel.GDELT_DOC, URL, "Canal", NOW, detected_at=NOW - timedelta(days=1)),
        Article("prensa", Channel.NEWS_SITEMAP, URL + "?utm_source=test", "Canal", NOW,
                published_at=NOW - timedelta(days=60), published_at_origin=PublicationDateOrigin.FEED),
    ])
    assert build.exclusion(item, NOW) == build.Exclusion.OUT_OF_WINDOW
    assert item.detected_at == NOW - timedelta(days=1)


@pytest.mark.parametrize("body", [b"", b"Please limit requests", b"{}", b'{"articles": null}', b'{"articles": [1]}'])
def test_failed_responses_do_not_break_offline_parse(tmp_path, body):
    store = RawStore(tmp_path)
    store.save("failure.json", Response("https://gdelt.test", body, {}))
    assert list(gdelt.parse(PR, store)) == []


def test_actual_url_host_controls_outlet_attribution(tmp_path):
    store = RawStore(tmp_path)
    store.save("capture.json", Response("https://gdelt.test", payload(url="https://evil.test/article", domain="prensa.com"), {}))
    assert list(gdelt.parse(PR, store)) == []


def test_capture_logs_429_bytes_then_success(monkeypatch, tmp_path):
    calls, delays = [], []
    url = "https://api.gdeltproject.org/test"
    def get(request_url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request_url, 429, "slow down", {"Retry-After": "45"}, io.BytesIO(b"throttle"))
        return Response(request_url, payload(), {})
    monkeypatch.setattr(gdelt.http, "get", get)
    monkeypatch.setattr(gdelt.time, "sleep", delays.append)
    monkeypatch.setattr(gdelt, "_last_request_at", float("-inf"))
    store = RawStore(tmp_path)
    assert len(gdelt._capture(url, store)) == 1
    first, second = store.records(FETCH_LOG)
    assert first["status"] == 429 and not first["complete"]
    assert (tmp_path / first["name"]).read_bytes() == b"throttle"
    assert first["sha256"] == hashlib.sha256(b"throttle").hexdigest()
    assert first["bytes"] == 8 and first["latency_seconds"] >= 0
    assert second["status"] == 200 and second["complete"]
    assert 45 in delays
    assert calls == [{"attempts": 1, "timeout": 60}] * 2


def test_exhausted_retries_preserve_timeout_attempts(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        raise TimeoutError("timeout")
    monkeypatch.setattr(gdelt.http, "get", timeout)
    monkeypatch.setattr(gdelt.time, "sleep", lambda _: None)
    monkeypatch.setattr(gdelt, "ATTEMPTS", 2)
    store = RawStore(tmp_path)
    with pytest.raises(RuntimeError, match="capture failed"):
        gdelt._capture("https://gdelt.test", store)
    assert len(store.records(FETCH_LOG)) == 2
    assert all(record["status"] is None and not record["complete"] for record in store.records(FETCH_LOG))


def test_capped_slice_is_split_without_gaps_and_completed_slices_skip(monkeypatch, tmp_path):
    from urllib.parse import parse_qs, urlsplit
    queries = []
    def capture(url, store):
        queries.append(parse_qs(urlsplit(url).query))
        return [{}] * (250 if len(queries) == 1 else 2)
    monkeypatch.setattr(gdelt, "_capture", capture)
    completed = set()
    end = NOW + timedelta(hours=1)
    gdelt._fetch_slice(GDELT_FEED.url, RawStore(tmp_path), NOW, end, completed)
    assert len(queries) == 3
    right, left = queries[1], queries[2]
    left_end = datetime.strptime(left["enddatetime"][0], "%Y%m%d%H%M%S")
    right_start = datetime.strptime(right["startdatetime"][0], "%Y%m%d%H%M%S")
    assert right_start - left_end == timedelta(seconds=1)
    assert queries[0]["maxrecords"] == ["250"]
    assert len(completed) == 2
    gdelt._fetch_slice(GDELT_FEED.url, RawStore(tmp_path), NOW, end, completed)
    assert len(queries) == 4  # parent checked again, children resumed


def test_shared_gdelt_feed_is_fetched_once(monkeypatch):
    fetched = []
    monkeypatch.setattr(channels, "fetch", lambda source, feed: fetched.append(feed))
    assert ingest.ingest({"gdelt"}) == []
    assert fetched == [GDELT_FEED]
    fetched.clear()
    assert ingest.ingest({"prensa", "telemetro"}) == []
    assert len(fetched) == 2 and all(feed.channel == Channel.NEWS_SITEMAP for feed in fetched)


def test_news_sitemap_uses_publication_date(tmp_path):
    body = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"><url>
        <loc>https://www.prensa.com/economia/canal/</loc><lastmod>2026-10-07</lastmod>
        <news:news><news:title>Canal</news:title>
        <news:publication_date>2026-10-06T10:00:00-05:00</news:publication_date></news:news>
        </url></urlset>'''
    store = RawStore(tmp_path)
    store.save("capture.xml", Response("https://prensa.test", body, {}))
    [item] = news_sitemap.parse(PR, store)
    assert item.published_at == datetime(2026, 10, 6, 15, tzinfo=UTC)
    assert item.published_at_origin == PublicationDateOrigin.FEED


def test_offline_build_is_deterministic_with_detection_only_rows(monkeypatch, tmp_path):
    dates = [NOW - timedelta(days=2), NOW - timedelta(days=1)]
    monkeypatch.setattr(build.channels, "parse", lambda source, feed: (
        [Article(source.key, Channel.GDELT_DOC, URL, "Canal", NOW, detected_at=dates[0])]
        if source == PR and feed == GDELT_FEED else []
    ))
    for name in ("NEWS_CSV", "EXCLUDED_NEWS_CSV", "SOURCES_JSON", "NEWS_QUALITY_JSON"):
        monkeypatch.setattr(build, name, tmp_path / name)
    monkeypatch.setattr(build, "PROCESSED", tmp_path)
    report = build.build()
    first = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    build.build()
    assert first == {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert report["incluidas"] == 1
    assert report["incluidas_por_origen_fecha"] == {"deteccion_gdelt": 1}


def test_processed_json_uses_platform_stable_newlines(tmp_path):
    output = tmp_path / "report.json"
    write_json(output, {"title": "Panamá", "rows": [1, 2]})
    assert b"\r" not in output.read_bytes()
    assert json.loads(output.read_bytes()) == {"title": "Panamá", "rows": [1, 2]}
