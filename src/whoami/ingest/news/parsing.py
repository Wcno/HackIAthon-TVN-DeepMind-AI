"""Dates, text and URLs as feeds publish them."""

import html
import re
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

PANAMA = timezone(timedelta(hours=-5), "America/Panama")
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def parse_iso(raw: str | None) -> datetime | None:
    """ISO 8601. A missing offset means UTC, as in WordPress `date_gmt`."""
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)


def parse_rss_date(raw: str | None) -> datetime | None:
    """RFC 822, or Panamá América's `Tue, 10/06/2026 - 17:30` in Panama time."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).astimezone(UTC)
    except (TypeError, ValueError):
        pass
    try:
        local = datetime.strptime(raw, "%a, %m/%d/%Y - %H:%M")
    except ValueError:
        return None
    return local.replace(tzinfo=PANAMA).astimezone(UTC)


def clean_text(raw: str | None) -> str | None:
    """Plain text from feed HTML: tags stripped, entities decoded, spaces collapsed."""
    if not raw:
        return None
    return _SPACES.sub(" ", html.unescape(_TAG.sub(" ", raw))).strip() or None


def section_of(url: str) -> str | None:
    """First path segment, which these outlets use as the section."""
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    return segments[0] if len(segments) > 1 else None


def canonical_url(url: str) -> str:
    """Same article despite scheme, `www.`, query, fragment or trailing slash."""
    parts = urlsplit(url.strip())
    return parts.netloc.lower().removeprefix("www.") + parts.path.rstrip("/")


def belongs_to_outlet(url: str | None, domain: str) -> bool:
    """Exact HTTP URL host matching; metadata domain labels do not control attribution."""
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return parts.scheme in {"http", "https"} and (parts.hostname or "").removeprefix("www.") == domain.removeprefix("www.")
    except ValueError:
        return False
