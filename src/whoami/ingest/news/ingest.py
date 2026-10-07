"""Download every news feed to raw. One failing feed does not stop the others."""

from whoami.ingest.news import channels
from whoami.ingest.news.sources import SOURCES


def ingest(only: set[str] | None = None) -> list[str]:
    """Returns the feeds that failed."""
    failures = []
    for source in SOURCES:
        if only and source.key not in only:
            continue
        for feed in source.feeds:
            label = f"{source.key}/{feed.channel}"
            print(f"  {label} ...", flush=True)
            try:
                channels.fetch(source, feed)
            except Exception as error:
                print(f"  {label} FAILED: {type(error).__name__}: {error}")
                failures.append(label)
    return failures
