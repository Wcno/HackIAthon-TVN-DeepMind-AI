from datetime import UTC, datetime
import json

from whoami.contracts import EVENTS_PROPERTIES
from whoami.ingest import usgs
from whoami.ingest.http import Response
from whoami.ingest.raw import RawStore

WINDOW_END = datetime(2026, 10, 7, tzinfo=UTC)


def raw_event(time_millis: int | None = 1_759_564_271_000) -> dict:
    return {
        "type": "Feature",
        "id": "us6000rerc",
        "properties": {
            "mag": 4.5,
            "time": time_millis,
            "updated": 1_766_184_595_000,
            "place": "195 km S of Burica, Panama",
            "status": "reviewed",
            "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000rerc",
            "tsunami": 0,
        },
        "geometry": {"type": "Point", "coordinates": [-82.7069, 6.2706, 10]},
    }


def test_feature_properties_are_exactly_the_contract_fields():
    feature = usgs.map_feature(raw_event())

    assert tuple(feature["properties"]) == EVENTS_PROPERTIES
    assert feature["properties"]["magnitude"] == 4.5
    assert (feature["properties"]["longitude"], feature["properties"]["latitude"], feature["properties"]["depth"]) == (
        -82.7069,
        6.2706,
        10,
    )


def test_times_are_iso_8601_utc():
    millis = int(datetime(2025, 10, 4, 7, 31, 11, tzinfo=UTC).timestamp() * 1000)

    properties = usgs.map_feature(raw_event(millis))["properties"]

    assert properties["time"] == "2025-10-04T07:31:11Z"
    assert properties["updated"] == "2025-12-19T22:49:55Z"


def test_event_inside_window_is_kept():
    assert usgs.exclusion(usgs.map_feature(raw_event()), WINDOW_END) is None


def test_event_before_window_start_is_excluded():
    before = int(datetime(2025, 10, 1, 23, 59, tzinfo=UTC).timestamp() * 1000)

    assert usgs.exclusion(usgs.map_feature(raw_event(before)), WINDOW_END) == usgs.OUT_OF_WINDOW


def test_event_after_extraction_is_excluded():
    after = int(datetime(2026, 10, 8, tzinfo=UTC).timestamp() * 1000)

    assert usgs.exclusion(usgs.map_feature(raw_event(after)), WINDOW_END) == usgs.OUT_OF_WINDOW


def test_event_without_time_is_excluded_not_dropped_silently():
    assert usgs.exclusion(usgs.map_feature(raw_event(None)), WINDOW_END) == usgs.NO_TIME


def test_geojson_build_uses_platform_stable_newlines(monkeypatch, tmp_path):
    store = RawStore(tmp_path / "raw")
    store.save(usgs.RAW_NAME, Response("https://usgs.test", json.dumps({"features": [raw_event()]}).encode(), {}))
    output = tmp_path / "processed"
    monkeypatch.setattr(usgs, "STORE", store)
    monkeypatch.setattr(usgs, "PROCESSED", output)
    monkeypatch.setattr(usgs, "EVENTS_GEOJSON", output / "eventos.geojson")
    monkeypatch.setattr(usgs, "EVENTS_QUALITY_JSON", output / "quality.json")
    assert usgs.build()["incluidos"] == 1
    assert b"\r" not in (output / "eventos.geojson").read_bytes()
