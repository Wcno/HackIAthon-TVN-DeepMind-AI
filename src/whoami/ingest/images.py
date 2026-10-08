"""The photo of each news item: its page's og:image (or twitter:image), for the agenda and the case header.

Only the topics shown on the agenda are fetched, one polite request per article. The result, id_noticia -> photo,
lives beside the processed data in imagenes.json; the app shows each photo credited to its outlet and linked to the
article. A page without a usable image simply has no photo.
"""

import json
from collections.abc import Callable, Iterable
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from whoami.ingest import http

IMAGES_JSON = "imagenes.json"
PREFERRED = ("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src")


class _MetaImages(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        values = {key.lower(): value for key, value in attrs if value}
        key = (values.get("property") or values.get("name") or "").lower()
        if key in PREFERRED and "content" in values:
            self.found.setdefault(key, values["content"])


def og_image(html: str, page_url: str) -> str | None:
    """The page's representative image as an absolute http(s) URL, or None."""
    parser = _MetaImages()
    parser.feed(html)
    for key in PREFERRED:
        if key in parser.found:
            url = urljoin(page_url, unescape(parser.found[key]).strip())
            if urlsplit(url).scheme in ("http", "https"):
                return url
    return None


def collect(groups: Iterable[dict], fetch: Callable[[str], str], *, limit: int | None = None) -> dict[str, dict]:
    """Photos for the news of the first `limit` groups; an article that fails to load is skipped."""
    images = {}
    for position, group in enumerate(groups):
        if limit is not None and position >= limit:
            break
        for member in group["miembros"]:
            try:
                url = og_image(fetch(member["url"]), member["url"])
            except (OSError, ValueError, UnicodeError):
                continue
            if url:
                images[member["id_noticia"]] = {"url": url, "credito": f"Foto: {member['medio']}",
                                                "enlace": member["url"], "ilustrativa": False}
    return images


def fetch_html(url: str) -> str:
    response = http.get(url, attempts=2, backoff_seconds=2.0, timeout=20)
    return response.body[:2_000_000].decode("utf-8", errors="replace")


def load(directory: Path) -> dict[str, dict]:
    path = directory / IMAGES_JSON
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write(directory: Path, images: dict[str, dict]) -> Path:
    path = directory / IMAGES_JSON
    path.write_text(json.dumps(dict(sorted(images.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                    newline="\n")
    return path
