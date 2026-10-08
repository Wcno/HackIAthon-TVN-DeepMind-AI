"""Download every news feed to raw. One failing feed does not stop the others."""

from whoami.ingest.news import channels
from whoami.ingest.news.sources import SOURCES, Channel


def ingest(only: set[str] | None = None) -> list[str]:
    """Returns the feeds that failed."""
    failures = []
    fetched = set()
    for source in SOURCES:
        if only and source.key not in only and not only & {"gdelt", "gdelt-gkg"}:
            continue
        for feed in source.feeds:
            if only and "gdelt" not in only and feed.channel == Channel.GDELT_DOC:
                continue
            if only and "gdelt-gkg" not in only and feed.channel == Channel.GDELT_GKG:
                continue
            if only and source.key not in only and feed.channel not in {Channel.GDELT_DOC, Channel.GDELT_GKG}:
                continue
            if feed in fetched:
                continue
            fetched.add(feed)
            label = f"{source.key}/{feed.channel}"
            print(f"  {label} ...", flush=True)
            try:
                channels.fetch(source, feed)
            except Exception as error:
                print(f"  {label} FAILED: {type(error).__name__}: {error}")
                failures.append(label)
    return failures
