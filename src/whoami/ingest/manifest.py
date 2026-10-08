"""`data/manifest.json` (§7): what the snapshot holds and how to reproduce it (T01).

Built last, only from the raw fetch logs and the processed files, so it is as
deterministic as the builds before it.
"""

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from whoami.contracts import (
    DATA,
    EVENTS_WINDOW_START,
    INEC_FROM_YEAR,
    MANIFEST_JSON,
    NEWS_WINDOW,
    PROCESSED,
    RAW,
)
from whoami.ingest import inec, usgs, worldbank
from whoami.ingest.news.sources import SOURCES
from whoami.ingest.output import iso, write_json
from whoami.ingest.raw import FETCH_LOG, RawStore

TRANSFORMATIONS = (
    "GDELT: seendate se conserva como fecha_deteccion, nunca como fecha_publicacion; "
    "se usa detección para la ventana solo si falta publicación. Capturas y errores se conservan sin modificar.",
    "Noticias: deduplicación por URL canónica; fecha de publicación del feed, de la página (artículos reeditados) "
    f"o del lastmod del sitemap; ventana de {NEWS_WINDOW.days} días hasta la fecha de corte (D-04); "
    "excluidas con su motivo en noticias_excluidas.csv.",
    "Banco Mundial: una consulta por indicador; cuadrícula completa país x indicador x año; nulos conservados; "
    "unidad derivada del indicador.",
    f"USGS: caja lat 5 a 12, lon -86 a -76, magnitud >= 3, desde {iso(EVENTS_WINDOW_START)} (D-02); "
    "propiedades del §7 (mag -> magnitude).",
    f"INEC: CSV y XLSX decodificados a UTF-8 en formato largo desde {INEC_FROM_YEAR}; variación interanual del PIB "
    "calculada; períodos duplicados en origen excluidos.",
)


def build() -> dict:
    fetches = _fetches()
    processed = sorted(path for path in PROCESSED.iterdir() if path.is_file())
    hashes = {_relative(path): _sha256(path) for path in processed}
    cutoff = max(datetime.fromisoformat(fetch["fecha_descarga"]) for fetch in fetches)
    manifest = {
        "version": f"{cutoff:%Y%m%d}-{_sha256_text(json.dumps(hashes, sort_keys=True))[:8]}",
        "fecha_corte_UTC": iso(cutoff),
        "consultas": fetches,
        "cantidades": {_relative(path): count for path in processed if (count := _count(path)) is not None},
        "licencias": _licenses(),
        "sha256": hashes,
        "registros_extraidos_en_descarga": _extracted_records(),
        "transformaciones": list(TRANSFORMATIONS),
    }
    write_json(MANIFEST_JSON, manifest)
    return {"version": manifest["version"], "fecha_corte_UTC": manifest["fecha_corte_UTC"], "archivos": len(hashes)}


def _fetches() -> list[dict]:
    """Latest fetch of every raw file: the exact URL, so the snapshot can be reproduced."""
    return [
        {
            "archivo": _relative(file.path),
            "url": file.url,
            "sha256": file.sha256,
            "fecha_descarga": iso(file.fetched_at),
        }
        for log in sorted(RAW.rglob(FETCH_LOG))
        for file in RawStore(log.parent).files()
    ]


def _extracted_records() -> dict[str, str]:
    """Files written at fetch time without their source bytes, such as TVN page dates."""
    logged = {Path(fetch["archivo"]) for fetch in _fetches()}
    return {
        _relative(path): _sha256(path)
        for path in sorted(RAW.rglob("*"))
        if path.is_file() and path.name != FETCH_LOG and Path(_relative(path)) not in logged
    }


def _licenses() -> dict[str, str]:
    news = {f"noticias/{source.key}": source.reuse_terms for source in SOURCES}
    return news | {"banco_mundial": worldbank.LICENSE, "usgs": usgs.LICENSE, "inec": inec.LICENSE}


def _count(path: Path) -> int | None:
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as file:
            return sum(1 for _ in csv.DictReader(file))
    if path.suffix == ".geojson":
        return len(json.loads(path.read_text(encoding="utf-8"))["features"])
    if path.name == "fuentes.json":
        return len(json.loads(path.read_text(encoding="utf-8"))["fuentes"])
    return None


def _relative(path: Path) -> str:
    return path.relative_to(DATA).as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
