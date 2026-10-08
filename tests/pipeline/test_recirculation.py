from datetime import UTC, datetime, timedelta

from whoami.pipeline.recirculation import (
    RECIRCULATION_GAP,
    apply_recirculations,
    group_recirculations,
    metadata_recirculation,
)
from whoami.schemas import Member


def row(published, modified, origin="feed", news_id="N-1") -> dict:
    return {
        "id_noticia": news_id,
        "origen_fecha_publicacion": origin,
        "fecha_publicacion": published,
        "fecha_modificacion": modified,
    }


def test_the_gap_is_seven_days():
    assert RECIRCULATION_GAP == timedelta(days=7)


def test_a_feed_item_modified_much_later_is_a_recirculation():
    found = metadata_recirculation(row("2025-12-03T10:00:00Z", "2026-10-01T09:00:00Z"))

    assert found is not None
    assert found.original == datetime(2025, 12, 3, 10, tzinfo=UTC)
    assert found.republished == datetime(2026, 10, 1, 9, tzinfo=UTC)
    assert found.justification == "Republicada el 2026-10-01; publicación original 2025-12-03"


def test_page_dates_count_too():
    assert metadata_recirculation(row("2025-12-03T10:00:00Z", "2026-10-01T09:00:00Z", origin="pagina")) is not None


def test_lastmod_dates_are_ignored_because_they_are_not_a_publication_date():
    assert metadata_recirculation(row("2025-12-03T10:00:00Z", "2026-10-01T09:00:00Z", origin="lastmod")) is None


def test_a_modification_within_the_gap_is_not_a_recirculation():
    assert metadata_recirculation(row("2026-10-01T10:00:00Z", "2026-10-08T10:00:00Z")) is None


def test_a_missing_or_earlier_modification_date_is_not_a_recirculation():
    assert metadata_recirculation(row("2026-10-01T10:00:00Z", "")) is None
    assert metadata_recirculation(row("2026-10-01T10:00:00Z", "2026-09-01T10:00:00Z")) is None


def test_a_modification_date_without_zone_is_read_as_utc():
    found = metadata_recirculation(row("2025-12-03T10:00:00Z", "2026-10-01T09:00:00"))

    assert found is not None
    assert found.republished == datetime(2026, 10, 1, 9, tzinfo=UTC)


TITLE = "Gobierno anuncia plan de reactivación del sector turismo en Bocas del Toro"


def member(news_id, medium, title, published, republished=None) -> Member:
    return Member(
        id_noticia=news_id,
        titulo=title,
        url=f"https://example.test/{news_id}",
        medio=medium,
        procedencia=medium,
        fecha_publicacion=published,
        alcance_texto="titular_metadatos",
        recirculada_en=republished,
    )


def test_the_same_outlet_republishing_after_more_than_three_days_is_a_recirculation():
    first = member("N-1", "TVN", TITLE, datetime(2026, 9, 20, 12, tzinfo=UTC))
    again = member("N-2", "TVN", TITLE, datetime(2026, 10, 5, 12, tzinfo=UTC))

    [found] = group_recirculations([again, first])

    assert found.id_noticia == "N-2"
    assert found.original == first.fecha_publicacion
    assert found.republished == again.fecha_publicacion
    assert found.justification == "Republicada el 2026-10-05; publicación original 2026-09-20"


def test_within_three_days_or_from_another_outlet_is_not_a_recirculation():
    first = member("N-1", "TVN", TITLE, datetime(2026, 10, 3, 12, tzinfo=UTC))
    soon = member("N-2", "TVN", TITLE, datetime(2026, 10, 5, 12, tzinfo=UTC))
    other = member("N-3", "Otro Medio", TITLE, datetime(2026, 10, 20, 12, tzinfo=UTC))

    assert group_recirculations([first, soon, other]) == []


def test_a_member_already_recirculated_by_metadata_is_left_alone():
    first = member("N-1", "TVN", TITLE, datetime(2026, 9, 1, 12, tzinfo=UTC))
    marked = member("N-2", "TVN", TITLE, datetime(2026, 9, 10, 12, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC))

    assert group_recirculations([first, marked]) == []


def test_applying_recirculations_moves_the_publication_back_and_keeps_the_rest():
    first = member("N-1", "TVN", TITLE, datetime(2026, 9, 20, 12, tzinfo=UTC))
    again = member("N-2", "TVN", TITLE, datetime(2026, 10, 5, 12, tzinfo=UTC))

    applied = apply_recirculations([first, again], group_recirculations([first, again]))

    assert applied[0] == first
    assert applied[1].fecha_publicacion == first.fecha_publicacion
    assert applied[1].recirculada_en == again.fecha_publicacion
    assert applied[1].recirculada_en > applied[1].fecha_publicacion
