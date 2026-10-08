from dataclasses import dataclass
from datetime import datetime

from whoami.contracts import PublicationDateOrigin
from whoami.ingest.news.sources import Channel


@dataclass(frozen=True)
class Article:
    """One news item as a single channel reported it, before merging."""

    source: str
    channel: Channel
    url: str
    title: str | None
    fetched_at: datetime
    published_at: datetime | None = None
    published_at_origin: PublicationDateOrigin | None = None
    modified_at: datetime | None = None
    description: str | None = None
    section: str | None = None
    detected_at: datetime | None = None
