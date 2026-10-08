"""GKG multilingual ZIP fallback: six hourly batches, explicitly partial coverage.

Batch timestamps represent indexing time here. PAGE_TITLE supplies the headline;
publication dates can still be merged from the outlet's own RSS/sitemap.
Format: https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf
"""

import io
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from whoami.ingest import http
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import belongs_to_outlet, clean_text, section_of
from whoami.ingest.news.sources import Channel, Feed, Source
from whoami.ingest.raw import RawStore

SAMPLE_HOURS = 6


def fetch(feed: Feed, store: RawStore) -> None:
    """Bounded fallback, not a claimed 30-day backfill. Reruns reuse frozen ZIPs."""
    newest = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    existing = {file.name for file in store.files()}
    for offset in range(SAMPLE_HOURS):
        batch = newest - timedelta(hours=offset)
        name = f"{batch:%Y%m%d%H%M%S}.translation.gkg.csv.zip"
        if name in existing:
            continue
        started = time.monotonic()
        response = http.get(feed.url + name)
        # Validate before registering a successful archive; keep exact original ZIP bytes.
        list(_rows(response.body))
        store.save(name, response, metadata={
            "status": 200, "latency_seconds": round(time.monotonic() - started, 3),
            "bytes": len(response.body), "batch_utc": batch.isoformat(),
            "sample_interval_minutes": 60, "partial": True,
        })
        print(f"    GKG {batch.isoformat()}: {len(response.body)} bytes", flush=True)


def _rows(body: bytes) -> Iterator[list[str]]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with archive.open(name) as stream:
                for line in io.TextIOWrapper(stream, encoding="utf-8", errors="replace"):
                    fields = line.rstrip("\r\n").split("\t")
                    if len(fields) >= 27 and fields[2] == "1":
                        yield fields


def parse(source: Source, store: RawStore) -> Iterator[Article]:
    for file in store.files():
        for fields in _rows(file.read()):
            url = fields[4]
            if not belongs_to_outlet(url, source.domain):
                continue
            try:
                detected = datetime.strptime(fields[1], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            except ValueError:
                detected = None
            try:
                extras = ET.fromstring("<extras>" + fields[26] + "</extras>")
                title = clean_text(extras.findtext("PAGE_TITLE"))
            except ET.ParseError:
                title = None
            yield Article(
                source=source.key, channel=Channel.GDELT_GKG, url=url, title=title,
                fetched_at=file.fetched_at, detected_at=detected, section=section_of(url),
            )


def coverage(store: RawStore) -> dict:
    files = store.files()
    batches = sorted(file.name[:14] for file in files)
    return {
        "archivos": len(files), "lotes_UTC": batches, "parcial": True,
        "nota": "Muestra de lotes multilingües cada 60 minutos; no cubre continuamente los 30 días.",
    }
