"""G6: each topic shows a photo: the article's own (og:image) on real data, a labelled illustrative one in the demo."""

import pytest
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.service import EditorialService
from whoami.backend.settings import Settings
from whoami.ingest.images import collect, og_image

PAGE = "https://www.tvn-2.com/nacionales/canal/2026/10/05/nota/"


@pytest.mark.parametrize("html, expected", [
    ('<meta property="og:image" content="https://cdn.tvn-2.com/canal.jpg">', "https://cdn.tvn-2.com/canal.jpg"),
    ('<meta content="https://cdn.tvn-2.com/a.jpg?w=1200&amp;h=630" property="og:image" />', "https://cdn.tvn-2.com/a.jpg?w=1200&h=630"),
    ('<meta property="og:image" content="/fotos/canal.jpg">', "https://www.tvn-2.com/fotos/canal.jpg"),
    ('<meta name="twitter:image" content="https://cdn.tvn-2.com/tw.jpg">', "https://cdn.tvn-2.com/tw.jpg"),
    ('<meta property="og:image" content="data:image/png;base64,AAAA">', None),
    ("<title>Sin foto</title>", None),
])
def test_og_image_reads_the_article_photo(html, expected):
    assert og_image(f"<html><head>{html}</head></html>", PAGE) == expected


def test_collect_maps_each_news_item_to_its_photo_and_skips_failures():
    groups = [{"miembros": [{"id_noticia": "N-1", "url": "https://a.test/1", "medio": "TVN"},
                            {"id_noticia": "N-2", "url": "https://a.test/2", "medio": "La Prensa"}]},
              {"miembros": [{"id_noticia": "N-3", "url": "https://a.test/3", "medio": "Telemetro"}]}]
    pages = {"https://a.test/1": '<meta property="og:image" content="https://a.test/1.jpg">',
             "https://a.test/3": '<meta property="og:image" content="https://a.test/3.jpg">'}

    def fetch(url):
        if url not in pages:
            raise OSError("not found")
        return pages[url]

    images = collect(groups, fetch)
    assert images == {"N-1": {"url": "https://a.test/1.jpg", "credito": "Foto: TVN", "enlace": "https://a.test/1", "ilustrativa": False},
                      "N-3": {"url": "https://a.test/3.jpg", "credito": "Foto: Telemetro", "enlace": "https://a.test/3", "ilustrativa": False}}
    assert collect(groups, fetch, limit=1) == {"N-1": images["N-1"]}


def test_a_group_takes_the_first_photo_among_its_news_or_none(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        repository = client.app.state.repository
        member = repository.record("group", "G-002")["miembros"][-1]["id_noticia"]
        image = {"url": "https://a.test/x.jpg", "credito": "Foto: TVN", "enlace": "https://a.test/x", "ilustrativa": False}
        service = EditorialService(repository, images={member: image})
        assert service.group("G-002")["imagen"] == image
        assert service.group("G-001")["imagen"] is None


def test_the_demo_agenda_shows_labelled_illustrative_photos(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        html = client.get("/inbox").text
        assert '/static/img/demo/canal-agua-clara.jpg' in html
        assert "Imagen ilustrativa" in html and "commons.wikimedia.org" in html
        assert html.count('class="photo row__photo"') >= 5
        case = client.get("/cases/CASO-001").text
        assert 'class="photo case__photo' in case


def _jpeg(width: int, height: int) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "tomato").save(buffer, "JPEG")
    return buffer.getvalue()


def _photo(url: str) -> dict:
    return {"url": url, "credito": "Foto: TVN", "enlace": "https://a.test/n", "ilustrativa": False}


def test_vendor_stores_a_resized_webp_copy_and_records_its_local_path(tmp_path):
    from PIL import Image

    from whoami.ingest.images import vendor

    images = {"N-1": _photo("https://cdn.test/big.jpg")}
    vendored = vendor(images, tmp_path, lambda url: _jpeg(2000, 1000))
    assert vendored["N-1"]["local"] == "/static/img/news/N-1.webp"
    assert vendored["N-1"]["url"] == "https://cdn.test/big.jpg" and vendored["N-1"]["credito"] == "Foto: TVN"
    with Image.open(tmp_path / "N-1.webp") as stored:
        assert stored.format == "WEBP" and stored.size == (800, 400)


def test_vendor_does_not_upscale_small_photos(tmp_path):
    from PIL import Image

    from whoami.ingest.images import vendor

    vendor({"N-1": _photo("https://cdn.test/s.jpg")}, tmp_path, lambda url: _jpeg(300, 200))
    with Image.open(tmp_path / "N-1.webp") as stored:
        assert stored.size == (300, 200)


def test_vendor_is_idempotent_and_skips_failures_and_static_images(tmp_path):
    from whoami.ingest.images import vendor

    requested = []

    def fetch(url):
        requested.append(url)
        if "broken" in url:
            raise OSError("down")
        if "garbage" in url:
            return b"not an image"
        return _jpeg(900, 900)

    images = {"N-1": _photo("https://cdn.test/a.jpg"), "N-2": _photo("https://cdn.test/broken.jpg"),
              "N-3": _photo("https://cdn.test/garbage.jpg"), "N-4": {**_photo("/static/img/demo/x.jpg"), "ilustrativa": True}}
    first = vendor(images, tmp_path, fetch)
    assert "local" in first["N-1"] and "local" not in first["N-2"] and "local" not in first["N-3"] and "local" not in first["N-4"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["N-1.webp"]

    requested.clear()
    assert vendor(first, tmp_path, fetch)["N-1"] == first["N-1"]
    assert "https://cdn.test/a.jpg" not in requested


def test_an_entry_whose_vendored_file_vanished_is_downloaded_again(tmp_path):
    from whoami.ingest.images import vendor

    images = {"N-1": {**_photo("https://cdn.test/a.jpg"), "local": "/static/img/news/N-1.webp"}}
    assert vendor(images, tmp_path, lambda url: _jpeg(100, 100))["N-1"]["local"] == "/static/img/news/N-1.webp"
    assert (tmp_path / "N-1.webp").is_file()


def test_pages_never_reference_an_external_photo(tmp_path):
    external = {"url": "https://cdn.test/x.jpg", "credito": "Foto: TVN", "enlace": "https://a.test/x", "ilustrativa": False}
    with TestClient(create_app(Settings(database=tmp_path / "editorial.sqlite3"))) as client:
        repository = client.app.state.repository
        members = [m["id_noticia"] for g in repository.records("group") for m in g["miembros"]]
        client.app.state.editorial.images = {member: external for member in members}
        html = client.get("/inbox").text
        assert "cdn.test" not in html
        assert "/static/img/photo-placeholder.svg" in html
        local = {**external, "local": "/static/img/demo/canal-agua-clara.jpg"}
        client.app.state.editorial.images = {member: local for member in members}
        assert "/static/img/demo/canal-agua-clara.jpg" in client.get("/inbox").text
