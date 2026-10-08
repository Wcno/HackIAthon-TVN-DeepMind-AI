"""The photo of each news item: its page's og:image (or twitter:image), for the agenda and the case header.

Only the topics shown on the agenda are fetched, one polite request per article. The result, id_noticia -> photo,
lives beside the processed data in imagenes.json; the app shows each photo credited to its outlet and linked to the
article. A page without a usable image simply has no photo.

For the offline demo (T10) every real photo is also vendored: downloaded once, resized to a small WebP beside the
app's static files and recorded as `local`. The app only ever serves that copy, never the outlet's server.
"""

import io
import json
from collections.abc import Callable, Iterable
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError

from whoami.ingest import http

IMAGES_JSON = "imagenes.json"
STATIC_PREFIX = "/static/img/news/"
VENDOR_DIRECTORY = Path(__file__).resolve().parents[1] / "backend" / "static" / "img" / "news"
VENDORED_WIDTH = 800
VENDORED_QUALITY = 78
MAX_DOWNLOAD_BYTES = 15_000_000
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


def fetch_image(url: str) -> bytes:
    response = http.get(url, attempts=2, backoff_seconds=2.0, timeout=20)
    if len(response.body) > MAX_DOWNLOAD_BYTES:
        raise ValueError("image too large")
    return response.body


def resized_webp(data: bytes) -> bytes:
    """The photo at most VENDORED_WIDTH px wide (never upscaled), upright, as WebP."""
    with Image.open(io.BytesIO(data)) as source:
        photo = ImageOps.exif_transpose(source)
        photo = photo.convert("RGBA" if photo.mode in ("RGBA", "LA", "P") else "RGB")
        if photo.width > VENDORED_WIDTH:
            photo = photo.resize((VENDORED_WIDTH, round(photo.height * VENDORED_WIDTH / photo.width)), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        photo.save(output, "WEBP", quality=VENDORED_QUALITY, method=6)
        return output.getvalue()


def vendor(images: dict[str, dict], directory: Path, fetch: Callable[[str], bytes]) -> dict[str, dict]:
    """Each remote photo stored under `directory` as <id>.webp and recorded as `local`; idempotent.

    Photos already on disk are not downloaded again; ones that fail to download or decode keep no `local`.
    """
    directory.mkdir(parents=True, exist_ok=True)
    vendored = {}
    for news_id, image in images.items():
        entry = {key: value for key, value in image.items() if key != "local"}
        if urlsplit(image["url"]).scheme in ("http", "https"):
            target = directory / f"{news_id}.webp"
            try:
                if not target.is_file():
                    target.write_bytes(resized_webp(fetch(image["url"])))
                entry["local"] = f"{STATIC_PREFIX}{target.name}"
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                pass
        vendored[news_id] = entry
    return vendored


def load(directory: Path) -> dict[str, dict]:
    path = directory / IMAGES_JSON
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write(directory: Path, images: dict[str, dict]) -> Path:
    path = directory / IMAGES_JSON
    path.write_text(json.dumps(dict(sorted(images.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                    newline="\n")
    return path
