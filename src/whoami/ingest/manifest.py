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
    PROCESSED_MANIFEST_JSON,
    RAW,
)
from whoami.ingest import inec, usgs, worldbank
from whoami.ingest.news.sources import SOURCES
from whoami.ingest.output import iso, write_json
from whoami.ingest.raw import FETCH_LOG, RawStore

TRANSFORMATIONS = (
    "GDELT: la fecha en que GDELT detectó la noticia se guarda como fecha de detección y nunca como fecha de publicación; "
    "solo se usa para la ventana si falta la publicación. Las capturas y los errores se conservan sin modificar.",
    "Noticias: deduplicación por URL canónica; la fecha de publicación sale del feed, de la página (artículos reeditados) "
    f"o de la fecha de última modificación del sitemap; ventana de {NEWS_WINDOW.days} días hasta la fecha de corte (D-04); "
    "las excluidas se listan con su motivo en noticias_excluidas.csv.",
    "Banco Mundial: una consulta por indicador; cuadrícula completa de país por indicador por año; los nulos se conservan; "
    "la unidad se deriva del indicador.",
    f"USGS: caja de latitud 5 a 12 y longitud -86 a -76, magnitud de 3 o más, desde {iso(EVENTS_WINDOW_START)} (D-02); "
    "se usan las propiedades del contrato de datos (la magnitud se guarda como magnitude).",
    f"INEC: CSV y XLSX decodificados a UTF-8 y puestos en formato largo (una fila por serie y período) desde {INEC_FROM_YEAR}; "
    "la variación interanual del PIB se calcula; los períodos duplicados en origen se excluyen.",
)


def build() -> dict:
    fetches = _fetches()
    processed = sorted(path for path in PROCESSED.iterdir() if path.is_file() and path != PROCESSED_MANIFEST_JSON)
    hashes = {_relative(path): _sha256(path) for path in processed}
    cutoff = max(datetime.fromisoformat(fetch["fecha_descarga"]) for fetch in fetches)
    manifest = {
        "version": _version(cutoff, hashes),
        "fecha_corte_UTC": iso(cutoff),
        "consultas": fetches,
        "cantidades": {_relative(path): count for path in processed if (count := _count(path)) is not None},
        "licencias": _licenses(),
        "sha256": hashes,
        "registros_extraidos_en_descarga": _extracted_records(),
        "transformaciones": list(TRANSFORMATIONS),
    }
    write_json(MANIFEST_JSON, manifest)
    write_json(PROCESSED_MANIFEST_JSON, manifest)
    return {"version": manifest["version"], "fecha_corte_UTC": manifest["fecha_corte_UTC"], "archivos": len(hashes)}


def refresh(paths: list[Path], data: Path = DATA) -> dict:
    """Re-hash only `paths` (files under `data` rewritten after `build`) and the version derived from the hashes.

    Everything else in the manifest is kept as built, so a rewrite of one file does not touch the rest.
    """
    manifest = json.loads((data / MANIFEST_JSON.name).read_text(encoding="utf-8"))
    for path in paths:
        manifest["sha256"][path.relative_to(data).as_posix()] = _sha256(path)
    manifest["version"] = _version(datetime.fromisoformat(manifest["fecha_corte_UTC"]), manifest["sha256"])
    write_json(data / MANIFEST_JSON.name, manifest)
    write_json(data / PROCESSED_MANIFEST_JSON.relative_to(DATA), manifest)
    return {"version": manifest["version"], "archivos": len(manifest["sha256"])}


def _version(cutoff: datetime, hashes: dict[str, str]) -> str:
    return f"{cutoff:%Y%m%d}-{_sha256_text(json.dumps(hashes, sort_keys=True))[:8]}"


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
