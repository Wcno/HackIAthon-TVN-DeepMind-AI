import io
import zipfile
from datetime import UTC, datetime

from whoami.ingest.http import Response
from whoami.ingest.news import ingest
from whoami.ingest.news.channels import gdelt_gkg
from whoami.ingest.news.sources import GDELT_GKG_FEED, SOURCES, Channel
from whoami.ingest.raw import RawStore

PR = next(source for source in SOURCES if source.key == "prensa")


def archive(url="https://www.prensa.com/economia/canal/", date="20261007210000", title=True):
    fields = ["20261007210000-T1", date, "1", "prensa.com", url] + [""] * 22
    fields[26] = "<PAGE_TITLE>Canal &amp; tr&#xE1;nsitos</PAGE_TITLE>" if title else ""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr("batch.csv", "\t".join(fields).encode())
    return output.getvalue()


def test_gkg_preserves_headline_and_index_time_without_publication(tmp_path):
    store = RawStore(tmp_path)
    store.save("batch.zip", Response("https://gdelt.test", archive(), {}))
    [article] = gdelt_gkg.parse(PR, store)
    assert article.title == "Canal & tránsitos"
    assert article.detected_at == datetime(2026, 10, 7, 21, tzinfo=UTC)
    assert article.published_at is None
    assert article.channel == Channel.GDELT_GKG


def test_gkg_does_not_match_domains_by_substring(tmp_path):
    store = RawStore(tmp_path)
    store.save("batch.zip", Response("https://gdelt.test", archive(url="https://evilprensa.com/article"), {}))
    assert list(gdelt_gkg.parse(PR, store)) == []


def test_gkg_retains_missing_fields_for_quality_exclusion(tmp_path):
    store = RawStore(tmp_path)
    store.save("batch.zip", Response("https://gdelt.test", archive(date="0", title=False), {}))
    [article] = gdelt_gkg.parse(PR, store)
    assert article.title is None and article.detected_at is None


def test_gkg_fetch_is_bounded_and_resumable(monkeypatch, tmp_path):
    calls = []
    def get(url):
        calls.append(url)
        return Response(url, archive(), {})
    monkeypatch.setattr(gdelt_gkg.http, "get", get)
    store = RawStore(tmp_path)
    gdelt_gkg.fetch(GDELT_GKG_FEED, store)
    gdelt_gkg.fetch(GDELT_GKG_FEED, store)
    assert len(calls) == 6
    assert all(url.endswith("translation.gkg.csv.zip") for url in calls)
    assert all(file.read() == archive() for file in store.files())
    assert gdelt_gkg.coverage(store)["parcial"] is True


def test_gkg_alias_selects_shared_feed_only(monkeypatch):
    fetched = []
    monkeypatch.setattr(ingest.channels, "fetch", lambda source, feed: fetched.append(feed))
    assert ingest.ingest({"gdelt-gkg"}) == []
    assert fetched == [GDELT_GKG_FEED]
