"""USGS earthquakes (§6.C): FDSN event service, built into `eventos.geojson`.

Seismic facts only, never evidence of floods or economic losses. The box is a region, not Panama's territory.
"""

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Final

from whoami.contracts import (
    EVENTS_GEOJSON,
    EVENTS_QUALITY_JSON,
    EVENTS_WINDOW_START,
    PROCESSED,
    RAW,
)
from whoami.ingest import http
from whoami.ingest.output import iso, write_json
from whoami.ingest.raw import RawStore

API: Final = "https://earthquake.usgs.gov/fdsnws/event/1/query"
BOX: Final = "minlatitude=5&maxlatitude=12&minlongitude=-86&maxlongitude=-76"
MIN_MAGNITUDE: Final = 3
LICENSE: Final = "Public domain (US government). Credit: U.S. Geological Survey, Department of the Interior/USGS"

STORE: Final = RawStore(RAW / "usgs")
RAW_NAME: Final = "eventos.geojson"
OUT_OF_WINDOW: Final = "fuera_de_ventana"
NO_TIME: Final = "sin_hora"


def fetch() -> list[str]:
    """Returns the failures, like the other ingesters."""
    print("  usgs ...", flush=True)
    try:
        STORE.save(RAW_NAME, http.get(query_url(datetime.now(UTC))))
    except Exception as error:
        print(f"  usgs FAILED: {type(error).__name__}: {error}")
        return ["usgs"]
    return []


def build() -> dict:
    [raw] = [file for file in STORE.files() if file.name == RAW_NAME]
    source = json.loads(raw.read())
    window_end = raw.fetched_at

    features, excluded = [], Counter()
    for item in source["features"]:
        feature = map_feature(item)
        reason = exclusion(feature, window_end)
        if reason:
            excluded[reason] += 1
        else:
            features.append(feature)
    features.sort(key=lambda feature: (feature["properties"]["time"], feature["properties"]["id"]))

    PROCESSED.mkdir(parents=True, exist_ok=True)
    collection = {
        "type": "FeatureCollection",
        "fuente_url": raw.url,
        "fecha_extraccion": iso(raw.fetched_at),
        "licencia": LICENSE,
        "features": features,
    }
    EVENTS_GEOJSON.write_text(json.dumps(collection, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    report = quality_report(features, excluded, len(source["features"]), window_end)
    write_json(EVENTS_QUALITY_JSON, report)
    return report


def query_url(until: datetime) -> str:
    return (
        f"{API}?format=geojson&{BOX}&minmagnitude={MIN_MAGNITUDE}"
        f"&starttime={iso(EVENTS_WINDOW_START)}&endtime={iso(until)}&orderby=time-asc"
    )


def map_feature(item: dict) -> dict:
    """USGS calls the magnitude `mag` and keeps depth inside the coordinates; the contract wants flat fields."""
    source = item["properties"]
    longitude, latitude, depth = item["geometry"]["coordinates"]
    properties = {
        "id": item["id"],
        "magnitude": source["mag"],
        "time": _from_millis(source["time"]),
        "updated": _from_millis(source["updated"]),
        "longitude": longitude,
        "latitude": latitude,
        "depth": depth,
        "place": source["place"],
        "status": source["status"],
        "url": source["url"],
    }
    return {"type": "Feature", "properties": properties, "geometry": {"type": "Point", "coordinates": [longitude, latitude, depth]}}


def exclusion(feature: dict, window_end: datetime) -> str | None:
    time = feature["properties"]["time"]
    if time is None:
        return NO_TIME
    if not iso(EVENTS_WINDOW_START) <= time <= iso(window_end):
        return OUT_OF_WINDOW
    return None


def quality_report(features: list[dict], excluded: Counter, read: int, window_end: datetime) -> dict:
    times = [feature["properties"]["time"] for feature in features]
    magnitudes = [m for feature in features if (m := feature["properties"]["magnitude"]) is not None]
    return {
        "ventana": {"desde": iso(EVENTS_WINDOW_START), "hasta": iso(window_end)},
        "eventos_leidos": read,
        "incluidos": len(features),
        "excluidos_por_motivo": dict(excluded.most_common()),
        "primer_evento": times[0] if times else None,
        "ultimo_evento": times[-1] if times else None,
        "magnitud": {"minima": min(magnitudes), "maxima": max(magnitudes)} if magnitudes else None,
    }


def _from_millis(millis: int | None) -> str | None:
    return iso(datetime.fromtimestamp(millis / 1000, UTC)) if millis is not None else None
