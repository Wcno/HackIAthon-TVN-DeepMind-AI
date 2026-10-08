"""Raw news to `noticias.csv`, offline and deterministic: the same raw always gives the same files.

Steps: parse every channel, merge the same URL into one row, keep rows inside
the window and record every exclusion with its reason (T01 quality report).
`fuentes.json` catalogs each source with its reuse conditions (§6.A).
"""

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from whoami.contracts import (
    EXCLUDED_NEWS_COLUMNS,
    EXCLUDED_NEWS_CSV,
    NEWS_COLUMNS,
    NEWS_CSV,
    NEWS_QUALITY_JSON,
    PROCESSED,
    SOURCES_JSON,
    TEXT_SCOPE_DESCRIPTION,
    TEXT_SCOPE_HEADLINE,
    PublicationDateOrigin,
    news_window_start,
)
from whoami.ingest.news import channels
from whoami.ingest.news.channels import gdelt, gdelt_gkg
from whoami.ingest.news.article import Article
from whoami.ingest.news.parsing import canonical_url
from whoami.ingest.news.sources import GDELT_FEED, GDELT_GKG_FEED, SOURCES, Channel, Source
from whoami.ingest.output import iso, write_csv, write_json


class Exclusion(StrEnum):
    INVALID_URL = "url_invalida"
    NO_TITLE = "sin_titulo"
    NO_DATE = "sin_fecha"
    OUT_OF_WINDOW = "fuera_de_ventana"


@dataclass(frozen=True)
class NewsItem:
    """One article after merging every channel and capture that reported its URL."""

    id: str
    source: Source
    url: str
    title: str | None
    channels: tuple[Channel, ...]
    fetched_at: datetime
    published_at: datetime | None
    published_at_origin: PublicationDateOrigin | None
    modified_at: datetime | None
    description: str | None
    section: str | None
    detected_at: datetime | None = None

    @property
    def window_date(self) -> datetime | None:
        return self.published_at or self.detected_at


def build() -> dict:
    articles = [
        article
        for source in SOURCES
        for feed in source.feeds
        for article in channels.parse(source, feed)
    ]
    items = merge(articles)
    cutoff = max((article.fetched_at for article in articles), default=datetime.now(UTC))
    kept, excluded = [], []
    for item in items:
        reason = exclusion(item, cutoff)
        if reason:
            excluded.append((item, reason))
        else:
            kept.append(item)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    write_csv(NEWS_CSV, NEWS_COLUMNS, (_news_row(item) for item in _newest_first(kept)))
    write_csv(
        EXCLUDED_NEWS_CSV,
        EXCLUDED_NEWS_COLUMNS,
        (_excluded_row(item, reason) for item, reason in sorted(excluded, key=lambda pair: pair[0].id)),
    )
    write_json(SOURCES_JSON, {"fuentes": [_source_entry(source, articles, kept) for source in SOURCES]})
    report = _quality_report(articles, kept, excluded, cutoff)
    write_json(NEWS_QUALITY_JSON, report)
    return report


def merge(articles: Iterable[Article]) -> list[NewsItem]:
    groups: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        groups[canonical_url(article.url)].append(article)
    sources = {source.key: source for source in SOURCES}
    return [_merge_group(group, sources) for group in groups.values()]


def exclusion(item: NewsItem, cutoff: datetime) -> Exclusion | None:
    try:
        parsed = urlsplit(item.url)
        if (parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username
                or any(char.isspace() or ord(char) < 32 for char in item.url)):
            return Exclusion.INVALID_URL
        parsed.port
    except ValueError:
        return Exclusion.INVALID_URL
    if not item.title:
        return Exclusion.NO_TITLE
    if item.window_date is None:
        return Exclusion.NO_DATE
    if not news_window_start(cutoff) <= item.window_date <= cutoff:
        return Exclusion.OUT_OF_WINDOW
    return None


def news_id(url: str) -> str:
    """Stable across rebuilds: derived from the canonical URL, not from row order."""
    return "N-" + hashlib.sha1(canonical_url(url).encode()).hexdigest()[:12]


def _merge_group(group: list[Article], sources: dict[str, Source]) -> NewsItem:
    """Earliest capture first, so each field keeps the first value seen for it."""
    group = sorted(group, key=lambda article: article.fetched_at)
    first = group[0]
    published_at, published_at_origin = _publication_date(group)
    return NewsItem(
        id=news_id(first.url),
        source=sources[first.source],
        url=first.url,
        title=_first(article.title for article in group),
        channels=tuple(sorted({article.channel for article in group})),
        fetched_at=first.fetched_at,
        published_at=published_at,
        published_at_origin=published_at_origin,
        modified_at=max((article.modified_at for article in group if article.modified_at), default=None),
        description=_first(article.description for article in group),
        section=_first(article.section for article in group),
        detected_at=min((article.detected_at for article in group if article.detected_at), default=None),
    )


def _publication_date(group: list[Article]) -> tuple[datetime | None, PublicationDateOrigin | None]:
    """Most reliable origin wins; `lastmod` is the fallback (docs/research/tvn-fecha-publicacion.md)."""
    for origin in (PublicationDateOrigin.FEED, PublicationDateOrigin.PAGE):
        dated = [article.published_at for article in group if article.published_at_origin == origin and article.published_at]
        if dated:
            return dated[0], origin
    lastmod = min((article.modified_at for article in group if article.modified_at), default=None)
    return lastmod, PublicationDateOrigin.LASTMOD if lastmod else None


def _first[T](values: Iterable[T | None]) -> T | None:
    return next((value for value in values if value), None)


def _newest_first(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(items, key=lambda item: (item.window_date, item.id), reverse=True)


def _news_row(item: NewsItem) -> dict:
    return {
        "id_noticia": item.id,
        "titulo": item.title,
        "url": item.url,
        "medio": item.source.name,
        "idioma": item.source.language,
        "fecha_publicacion": iso(item.published_at),
        "origen_fecha_publicacion": item.published_at_origin or "",
        "fecha_deteccion": iso(item.detected_at),
        "fecha_extraccion": iso(item.fetched_at),
        "tema": "",
        "origen": "+".join(item.channels),
        "alcance_texto": TEXT_SCOPE_DESCRIPTION if item.description else TEXT_SCOPE_HEADLINE,
        "id_fuente": item.source.key,
        "seccion": item.section or "",
        "descripcion": item.description or "",
        "fecha_modificacion": iso(item.modified_at),
    }


def _excluded_row(item: NewsItem, reason: Exclusion) -> dict:
    return {
        "id_noticia": item.id,
        "url": item.url,
        "id_fuente": item.source.key,
        "origen": "+".join(item.channels),
        "motivo": reason,
        "fecha_publicacion": iso(item.published_at),
    }


def _source_entry(source: Source, articles: list[Article], kept: list[NewsItem]) -> dict:
    fetched = [article.fetched_at for article in articles if article.source == source.key]
    return {
        "id_fuente": source.key,
        "medio": source.name,
        "dominio": source.domain,
        "tipo": source.kind,
        "idioma": source.language,
        "canales": [{"canal": feed.channel, "url": feed.url} for feed in source.feeds],
        "licencia": "Sin licencia abierta declarada",
        "condiciones_reutilizacion": source.reuse_terms,
        "fecha_consulta": iso(max(fetched, default=None)),
        "n_registros": sum(1 for item in kept if item.source == source),
    }


def _coverage(items: list[NewsItem], window_start: datetime, cutoff: datetime) -> dict:
    """Effective coverage per source (§6.A): which days of the window have at least one item."""
    days_in_window = (cutoff.date() - window_start.date()).days + 1
    coverage = {}
    for source in SOURCES:
        dates = sorted(item.window_date for item in items if item.source == source)
        days = {date.date() for date in dates}
        coverage[source.key] = {
            "incluidas": len(dates),
            "desde": iso(dates[0]) if dates else None,
            "hasta": iso(dates[-1]) if dates else None,
            "dias_con_noticias": len(days),
            "dias_sin_noticias": [
                day.isoformat()
                for offset in range(days_in_window)
                if (day := window_start.date() + timedelta(days=offset)) not in days
            ] if dates else "todos",
        }
    return coverage


def _quality_report(
    articles: list[Article], kept: list[NewsItem], excluded: list[tuple[NewsItem, Exclusion]], cutoff: datetime
) -> dict:
    kept_by_source = Counter(item.source.key for item in kept)
    window_start = news_window_start(cutoff)
    return {
        "ventana": {"desde": iso(window_start), "hasta": iso(cutoff)},
        "registros_leidos": len(articles),
        "noticias_unicas": len(kept) + len(excluded),
        "incluidas": len(kept),
        "excluidas_por_motivo": dict(Counter(reason.value for _, reason in excluded).most_common()),
        "cobertura_por_fuente": _coverage(kept, window_start, cutoff),
        "incluidas_por_origen_fecha": dict(Counter(
            item.published_at_origin.value if item.published_at_origin else "deteccion_gdelt"
            for item in kept
        ).most_common()),
        "gdelt": gdelt.coverage(SOURCES[0].store(GDELT_FEED)),
        "gdelt_gkg": gdelt_gkg.coverage(SOURCES[0].store(GDELT_GKG_FEED)),
        "umbrales_6A": {
            "minimo_100_noticias": len(kept) >= 100,
            "minimo_20_tvn": kept_by_source["tvn"] >= 20,
        },
    }

