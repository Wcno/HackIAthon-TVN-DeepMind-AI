"""Validate the frozen G1 snapshot and its reproducibility without network access.

Run with `uv run --locked python scripts/validate_g1.py`.
"""

import csv
import hashlib
import json
from collections import Counter

from whoami.contracts import DATA, MANIFEST_JSON, NEWS_CSV, PROCESSED, RAW
from whoami.ingest import http, inec, manifest, usgs, worldbank
from whoami.ingest.news import build
from whoami.ingest.output import write_json
from whoami.ingest.raw import FETCH_LOG, RawStore


def hashes() -> dict[str, str]:
    paths = sorted(PROCESSED.iterdir()) + [MANIFEST_JSON]
    return {path.relative_to(DATA).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


def no_network(*args, **kwargs):
    raise AssertionError("The offline build attempted an HTTP call")


def main() -> None:
    http.get = no_network
    for _ in range(2):
        news = build.build()
        worldbank.build()
        usgs.build()
        inec.build()
        manifest.build()
        current = hashes()
        if _ == 0:
            first = current
        else:
            assert first == current, "Rebuilding changed the frozen snapshot"

    document = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    for path, expected in document["sha256"].items():
        assert hashlib.sha256((DATA / path).read_bytes()).hexdigest() == expected, path
    raw_files = 0
    for log in RAW.rglob(FETCH_LOG):
        for file in RawStore(log.parent).files():
            assert hashlib.sha256(file.read()).hexdigest() == file.sha256, str(file.path)
            raw_files += 1

    with NEWS_CSV.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    indexed = {row["id_noticia"]: row for row in rows}
    gdelt_rows = [row for row in rows if "gdelt" in row["origen"]]
    assert gdelt_rows and all(row["fecha_deteccion"] for row in gdelt_rows)
    assert len({row["medio"] for row in gdelt_rows}) >= 2
    assert news["umbrales_6A"]["minimo_100_noticias"]
    assert news["umbrales_6A"]["minimo_20_tvn"]
    event_ids = ["N-a6f2bb0fa295", "N-c89a3928fe51", "N-095a7b20f510"]
    event = [indexed[article_id] for article_id in event_ids]
    assert len({row["medio"] for row in event}) == 3
    assert all("lau" in row["titulo"].lower() for row in event)
    report = {
        "offline_build": True, "identical_rebuilds": True, "manifest_hashes_valid": True,
        "raw_hashes_valid": raw_files, "news": len(rows), "gdelt_news": len(gdelt_rows),
        "gdelt_by_outlet": dict(Counter(row["medio"] for row in gdelt_rows)),
        "gdelt_without_publication": sum(not row["fecha_publicacion"] for row in gdelt_rows),
        "same_event_news_ids": event_ids, "gdelt_gkg": news["gdelt_gkg"],
        "gdelt_doc": news["gdelt"], "hashes": current,
    }
    output = DATA.parent / "outputs" / "validation" / "g1-runtime.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, report)
    print(json.dumps({key: value for key, value in report.items() if key != "hashes"}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
