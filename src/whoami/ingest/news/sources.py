"""Registry of news sources. Selection and rationale: docs/research/g1-data-sources.md."""

from dataclasses import dataclass
from enum import StrEnum

from whoami.contracts import RAW
from whoami.ingest.raw import RawStore


class Channel(StrEnum):
    TVN_SITEMAP = "tvn_sitemap"
    RSS = "rss"
    WP_API = "wp_api"
    NEWS_SITEMAP = "news_sitemap"
    GDELT_DOC = "gdelt_doc"
    GDELT_GKG = "gdelt_gkg"


class Kind(StrEnum):
    """Official press releases are primary evidence, not independent media coverage (CU-03)."""

    MEDIA = "medio"
    OFFICIAL = "oficial"


@dataclass(frozen=True)
class Feed:
    channel: Channel
    url: str


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    domain: str
    kind: Kind
    feeds: tuple[Feed, ...]
    reuse_terms: str
    language: str = "es"

    def store(self, feed: Feed) -> RawStore:
        if feed.channel == Channel.GDELT_DOC:
            return RawStore(RAW / "news" / "gdelt" / "doc")
        if feed.channel == Channel.GDELT_GKG:
            return RawStore(RAW / "news" / "gdelt" / "gkg")
        return RawStore(RAW / "news" / self.key / feed.channel)


MEDIA_TERMS = (
    "El sitio no publica condiciones de reutilización de sus feeds. "
    "Se conservan solo metadatos (titular, URL, fecha, sección) y la descripción breve del feed."
)
OFFICIAL_TERMS = (
    "Comunicados de prensa de una entidad pública sin condiciones de reutilización declaradas. "
    "Se conservan solo metadatos (titular, URL, fecha, categoría) y el extracto que publica su API."
)


def _official(key: str, name: str, domain: str, reuse_terms: str = OFFICIAL_TERMS) -> Source:
    return Source(key, name, domain, Kind.OFFICIAL, (Feed(Channel.WP_API, f"https://{domain}"),), reuse_terms)


GDELT_FEED = Feed(Channel.GDELT_DOC, "https://api.gdeltproject.org/api/v2/doc/doc")
GDELT_GKG_FEED = Feed(Channel.GDELT_GKG, "https://data.gdeltproject.org/gdeltv2/")
GDELT_TERMS = (
    "Metadatos indexados por GDELT (https://www.gdeltproject.org/), con atribución. "
    "GDELT no transfiere derechos de los medios. Solo titular, URL y fecha de detección; "
    "seendate no es fecha de publicación."
)


def _media(key: str, name: str, domain: str, *feeds: Feed) -> Source:
    return Source(key, name, domain, Kind.MEDIA, (*feeds, GDELT_FEED, GDELT_GKG_FEED), MEDIA_TERMS + " " + GDELT_TERMS)


SOURCES: tuple[Source, ...] = (
    Source(
        key="tvn",
        name="TVN",
        domain="www.tvn-2.com",
        kind=Kind.MEDIA,
        feeds=(
            Feed(Channel.TVN_SITEMAP, "https://www.tvn-2.com/tvn_sitemap_index.xml"),
            Feed(Channel.RSS, "https://www.tvn-2.com/rss/"),
            GDELT_FEED,
            GDELT_GKG_FEED,
        ),
        reuse_terms=MEDIA_TERMS + " " + GDELT_TERMS,
    ),
    _media("prensa", "La Prensa", "www.prensa.com", Feed(Channel.NEWS_SITEMAP,
           "https://www.prensa.com/arc/outboundfeeds/news-sitemap/?outputType=xml")),
    _media("telemetro", "Telemetro", "www.telemetro.com", Feed(Channel.NEWS_SITEMAP,
           "https://www.telemetro.com/sitemap-news.xml")),
    _media("panamaamerica", "Panamá América", "www.panamaamerica.com.pa", Feed(Channel.RSS,
           "https://www.panamaamerica.com.pa/rss/recent/index.xml")),
    _media("laestrella", "La Estrella de Panamá", "www.laestrella.com.pa"),
    _media("midiario", "Mi Diario", "www.midiario.com"),
    _media("critica", "Crítica", "www.critica.com.pa"),
    _media("diaadia", "Día a Día", "www.diaadia.com.pa"),
    _media("rpctv", "RPC TV", "www.rpctv.com"),
    _official(
        "pancanal", "Autoridad del Canal de Panamá", "pancanal.com",
        OFFICIAL_TERMS + " Los términos del sitio de la ACP restringen la copia del contenido.",
    ),
    _official("sinaproc", "SINAPROC", "www.sinaproc.gob.pa"),
    _official("mef", "Ministerio de Economía y Finanzas", "www.mef.gob.pa"),
    _official("mici", "Ministerio de Comercio e Industrias", "www.mici.gob.pa"),
    _official("atp", "Autoridad de Turismo de Panamá", "www.atp.gob.pa"),
    _official("amp", "Autoridad Marítima de Panamá", "www.amp.gob.pa"),
)
