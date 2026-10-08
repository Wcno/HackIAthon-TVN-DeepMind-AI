"""Old news is never a new event (T03): a republished item keeps its original date and records when it came back.

Two rules, both returning the evidence they used so the justification can say why:
- A (metadata): the feed or page date is trustworthy and the modification date is far later.
- B (inside a group): the same outlet republished a near-identical headline days after the first time.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from whoami.pipeline.provenance import near_identical
from whoami.schemas import Member, parse_utc

RECIRCULATION_GAP = timedelta(days=7)  # a news item is not "updated" a week later: it came back
GROUP_REPUBLICATION_GAP = timedelta(days=3)  # an outlet repeating its own headline within days is follow-up, not repeat

#: Publication dates that come from the outlet itself; a `lastmod` date is only a sitemap timestamp.
_TRUSTED_DATE_ORIGINS = frozenset({"feed", "pagina"})


@dataclass(frozen=True)
class Recirculation:
    id_noticia: str
    original: datetime
    republished: datetime

    @property
    def justification(self) -> str:
        return f"Republicada el {self.republished:%Y-%m-%d}; publicación original {self.original:%Y-%m-%d}"


def _parse_modified(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def metadata_recirculation(row: dict) -> Recirculation | None:
    """Rule A."""
    modified = row.get("fecha_modificacion")
    if row["origen_fecha_publicacion"] not in _TRUSTED_DATE_ORIGINS or not modified:
        return None
    published = parse_utc(row["fecha_publicacion"])
    republished = _parse_modified(modified)
    if republished - published <= RECIRCULATION_GAP:
        return None
    return Recirculation(row["id_noticia"], original=published, republished=republished)


def group_recirculations(members: Sequence[Member]) -> list[Recirculation]:
    """Rule B."""
    found = []
    for member in sorted(members, key=lambda m: m.fecha_publicacion):
        if member.recirculada_en is not None:
            continue
        earlier = [
            other
            for other in members
            if other.medio == member.medio
            and member.fecha_publicacion - other.fecha_publicacion > GROUP_REPUBLICATION_GAP
            and near_identical(other.titulo, member.titulo)
        ]
        if earlier:
            original = min(other.fecha_publicacion for other in earlier)
            found.append(Recirculation(member.id_noticia, original=original, republished=member.fecha_publicacion))
    return found


def apply_recirculations(members: Sequence[Member], recirculations: Sequence[Recirculation]) -> list[Member]:
    by_id = {r.id_noticia: r for r in recirculations}

    def applied(member: Member) -> Member:
        found = by_id.get(member.id_noticia)
        if found is None:
            return member
        return member.model_copy(update={"fecha_publicacion": found.original, "recirculada_en": found.republished})

    return [applied(member) for member in members]
