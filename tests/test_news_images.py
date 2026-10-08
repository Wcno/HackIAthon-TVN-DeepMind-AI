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
