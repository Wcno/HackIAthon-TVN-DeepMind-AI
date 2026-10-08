"""Page models for the quality and methodology screens: plain data in, display-ready values out."""

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from whoami.backend.panama_time import MONTHS, day_label, day_year_label, panama, short_stamp, stamp
from whoami.backend.service import quality_report
from whoami.contracts import RULES_VERSION, SCORE_RANGES, SCORE_WEIGHTS


def thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def decimal(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".").replace(".", ",") or "0"


def fixed(value: float) -> str:
    """Spanish decimal with exactly two places, for scores and their points."""
    return f"{value:.2f}".replace(".", ",")


def spanish_decimals(text: str) -> str:
    """Justifications are written by the pipeline with decimal points; the editor reads decimal commas."""
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text)


def _loaded(report: dict) -> dict | None:
    return None if report.get("available") is False else report


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


# ----------------------------------------------------------------- quality

SOURCE_KINDS = {"tvn_sitemap": "sitemap", "rss": "RSS", "news_sitemap": "news sitemap", "wp_api": "comunicados"}
TYPE_LABELS = {"medio": "Medios", "oficial": "Entidades oficiales"}
EXCLUSION_REASONS = {"fuera_de_ventana": "fuera de la ventana"}
DATE_ORIGINS = {
    "lastmod": "Última modificación del sitemap (lastmod)",
    "feed": "Feed del medio",
    "deteccion_gdelt": "Detección de GDELT",
    "pagina": "Página del artículo (reeditado)",
}
HTTP_ERRORS = {"429": "demasiadas solicitudes"}
OFFICIAL_ACRONYMS = {"pancanal": "ACP", "sinaproc": "SINAPROC", "mef": "MEF", "mici": "MICI", "atp": "ATP", "amp": "AMP"}
INEC_SERIES = {"ipc": "IPC", "pib": "PIB trimestral"}
SERIES_QUALIFIERS = {
    "indice": "índice", "var_mensual": "variación mensual", "var_interanual": "variación interanual", "constante": "constante",
    "corriente": "corriente", "constante_var_interanual": "constante, variación interanual",
}
EXCLUSION_LABELS = {"mes_sin_publicar": "mes sin publicar", "periodo_duplicado": "período duplicado"}
GDELT_MARKERS = ("GDELT", "seendate")


def _join_spanish(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} y {items[-1]}"


def _kind(channels: list[dict]) -> str:
    kinds = list(dict.fromkeys(SOURCE_KINDS[channel["canal"]] for channel in channels if channel["canal"] in SOURCE_KINDS))
    return _join_spanish(kinds) if kinds else "GDELT"


def _panama_days(directory: Path) -> dict[str, set[date]]:
    days: dict[str, set[date]] = defaultdict(set)
    for row in _rows(directory / "noticias.csv"):
        published = row.get("fecha_publicacion") or row.get("fecha_deteccion")
        if published:
            days[row["id_fuente"]].add(panama(published).date())
    return days


def _window_days(window: dict) -> list[date]:
    first, last = panama(window["desde"]).date(), panama(window["hasta"]).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _coverage(news: dict, sources: list[dict], directory: Path) -> dict:
    window_days = _window_days(news["ventana"])
    has_days = (directory / "noticias.csv").exists()
    published = _panama_days(directory)
    groups: dict[str, list[dict]] = {}
    for source in sources:
        entry = news["cobertura_por_fuente"].get(source["id_fuente"], {})
        included = entry.get("incluidas", 0)
        active = published.get(source["id_fuente"], set()) & set(window_days)
        span = f"de {short_stamp(entry['desde'])} a {short_stamp(entry['hasta'])}" if included else ""
        groups.setdefault(source["tipo"], []).append({
            "name": source["medio"], "kind": _kind(source["canales"]), "included": included,
            "days": [day in active for day in window_days] if has_days else None,
            "active": len(active), "total": len(window_days),
            "range": (f"{len(active)} de {len(window_days)} días con noticias · {span}" if has_days else span.capitalize())
                     if included else "Todos los días de la ventana sin noticias",
        })
    return {"first": day_label(window_days[0]), "last": day_label(window_days[-1]), "has_days": has_days,
            "groups": [{"label": TYPE_LABELS.get(kind, kind), "sources": rows} for kind, rows in groups.items()]}


def _gdelt_notice(news: dict, sources: list[dict]) -> dict | None:
    gdelt = news.get("gdelt")
    if not gdelt or gdelt["consultas_completas"] >= gdelt["intentos"]:
        return None
    errors = gdelt["errores_por_estado"]
    failed = sum(errors.values())
    codes = _join_spanish([f"{code} ({HTTP_ERRORS[code]})" if code in HTTP_ERRORS else code for code in errors])
    attempts = gdelt["intentos"]
    headline = "GDELT no completó ninguna consulta." if gdelt["consultas_completas"] == 0 else (
        f"GDELT completó {gdelt['consultas_completas']} de {attempts} consultas.")
    body = f" Hubo {attempts} intentos y {'los ' if failed == attempts else ''}{failed} respondieron con error {codes}." if failed else ""
    gkg = news.get("gdelt_gkg")
    if gkg:
        batches = sorted({panama(f"{batch[:4]}-{batch[4:6]}-{batch[6:8]}T{batch[8:10]}:00:00+00:00").date() for batch in gkg["lotes_UTC"]})
        when = f"del {day_label(batches[0])}" if len(batches) == 1 else f"del {day_label(batches[0])} al {day_label(batches[-1])}"
        body += f" De GDELT GKG solo hay una muestra de {gkg['archivos']} lotes por hora {when}; no cubre los {_window_length(news)} días."
    dependent = [s["medio"] for s in sources if news["cobertura_por_fuente"].get(s["id_fuente"], {}).get("incluidas", 1) == 0
                 and all(c["canal"].startswith("gdelt") for c in s["canales"])]
    if dependent:
        body += f" {_join_spanish(dependent)} dependen de GDELT y quedaron sin noticias."
    return {"headline": headline, "body": body.strip()}


def _window_length(news: dict) -> int:
    return (datetime.fromisoformat(news["ventana"]["hasta"]) - datetime.fromisoformat(news["ventana"]["desde"])).days


def _news_section(news: dict, sources: list[dict], directory: Path) -> dict:
    read, unique, kept = news["registros_leidos"], news["noticias_unicas"], news["incluidas"]
    excluded = news["excluidas_por_motivo"]
    repeated = read - unique

    def share(count: int) -> str:
        return f"{count / read * 100:.2f}%"

    segments = [{"kind": "kept", "width": share(kept), "count": kept, "label": "incluidas",
                 "note": "Dentro de la ventana, con su fecha de publicación."}]
    for reason, count in excluded.items():
        segments.append({"kind": "window" if reason == "fuera_de_ventana" else "other", "width": share(count), "count": count,
                         "label": EXCLUSION_REASONS.get(reason, reason.replace("_", " ")), "reason": reason})
    segments.append({"kind": "dup", "width": share(repeated), "count": repeated, "label": "repetidas",
                     "note": f"Misma URL canónica: {thousands(read)} leídos menos {thousands(unique)} únicas."})
    thresholds = []
    for key, passed in news.get("umbrales_6A", {}).items():
        minimum = re.fullmatch(r"minimo_(\d+)_(\w+)", key)
        if minimum:
            owner = " de TVN" if minimum[2] == "tvn" else ""
            thresholds.append({"passed": passed, "label": f"el mínimo de {minimum[1]} noticias{owner}"})
    origins = sorted(news.get("incluidas_por_origen_fecha", {}).items(), key=lambda item: -item[1])
    return {
        "window": f"Ventana de {_window_length(news)} días: del {stamp(news['ventana']['desde'])} al {stamp(news['ventana']['hasta'])}",
        "tally": {"read": read, "unique": unique, "kept": kept, "excluded": sum(excluded.values())},
        "segments": segments, "thresholds": thresholds,
        "coverage": _coverage(news, sources, directory), "notice": _gdelt_notice(news, sources),
        "origins": [{"label": DATE_ORIGINS.get(origin, origin), "count": count, "width": f"{count / kept * 100:.2f}%"}
                    for origin, count in origins] if kept else [],
    }


def _inec_labels(directory: Path) -> dict[str, str]:
    return {row["serie_id"]: row["serie"] for row in _rows(directory / "indicadores_inec.csv")}


def _period_label(period: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})", period)
    return f"{MONTHS[int(match[2]) - 1]} {match[1]}" if match else period


def _official_section(reports: dict, directory: Path) -> dict:
    worldbank, inec, events = (_loaded(reports[name]) for name in (
        "calidad_indicadores.json", "calidad_inec.json", "calidad_eventos.json"))
    grid = _rows(directory / "indicadores.csv")
    result: dict = {"worldbank": None, "inec": None, "usgs": None, "nulls": None, "inec_series": []}
    if worldbank:
        years = worldbank["anios"]
        countries, indicators = len({r["pais_iso3"] for r in grid}), len({r["indicador_id"] for r in grid})
        result["worldbank"] = {**worldbank, "period": f"{years['desde']} a {years['hasta']}",
                               "grid": (f"Cuadrícula completa de {countries} países, {indicators} indicadores y "
                                        f"{years['hasta'] - years['desde'] + 1} años.") if grid else None}
    if inec:
        excluded = inec["excluidos"]
        prefixes = list(dict.fromkeys(name.split("_")[0] for name in inec["series"]))
        base = next((r["base"] for r in _rows(directory / "indicadores_inec.csv") if r["serie_id"].startswith("ipc")), "")
        parts = []
        for prefix in prefixes:
            first = min(series["desde"] for name, series in inec["series"].items() if name.split("_")[0] == prefix)
            label = INEC_SERIES.get(prefix, prefix.upper())
            suffix = f" con base {base.split('=')[0]}" if prefix == "ipc" and base else ""
            parts.append(f"{label}{suffix} (desde {_period_label(first)})")
        result["inec"] = {**inec, "excluded": len(excluded), "from_year": inec["anio_inicial"], "summary": _join_spanish(parts) + "."}
        labels = _inec_labels(directory)
        rows = [{"series": _series_name(name, labels), "periods": series["nulos"], "kind": "null",
                 "what": "Nulo conservado: la fila queda sin valor."} for name, series in inec["series"].items() if series["nulos"]]
        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for item in excluded:
            grouped[(item["serie_id"], item["motivo"])].append(item)
        for (series_id, reason), items in grouped.items():
            detail = next((item["detalle"] for item in items if item.get("detalle")), "")
            what = f"Excluido: {EXCLUSION_LABELS.get(reason, reason.replace('_', ' '))}." + (f" {detail[0].upper()}{detail[1:]}." if detail else "")
            rows.append({"series": series_id.upper(), "periods": [item["periodo"] for item in items], "kind": "excluded", "what": what})
        result["nulls"] = rows
        result["inec_series"] = [{"name": _series_name(name, labels), **{k: series[k] for k in ("filas", "desde", "hasta")},
                                  "nulls": len(series["nulos"])} for name, series in inec["series"].items()]
    if events:
        result["usgs"] = {**events, "excluded": events["eventos_leidos"] - events["incluidos"],
                          "magnitude": f"{decimal(events['magnitud']['minima'], 1)} a {decimal(events['magnitud']['maxima'], 1)}",
                          "first": day_year_label(panama(events["primer_evento"])), "last": day_year_label(panama(events["ultimo_evento"]))}
    return result


def _series_name(series_id: str, labels: dict[str, str]) -> str:
    prefix, _, qualifier = series_id.partition("_")
    if prefix in INEC_SERIES and qualifier in SERIES_QUALIFIERS:
        return f"{prefix.upper()}, {SERIES_QUALIFIERS[qualifier]}" if prefix == "ipc" else f"{prefix.upper()} {SERIES_QUALIFIERS[qualifier]}"
    return labels.get(series_id) or series_id.replace("_", " ")


def _sentences(text: str) -> list[str]:
    return [sentence.strip().rstrip(".") for sentence in re.split(r"(?<=\.) ", re.sub(r" \(https?://[^)]*\)", "", text)) if sentence.strip()]


def _licence(text: str, *, head: str = "", gdelt: bool = False) -> str:
    sentences = [s for s in _sentences(text) if any(marker in s for marker in GDELT_MARKERS) == gdelt]
    return ". ".join([head, *sentences] if head else sentences).replace(" - ", ", ") + "."


def _download_times(downloads: list[str]) -> str:
    moments = sorted(panama(value) for value in downloads)
    first, last = short_stamp(moments[0].isoformat()), short_stamp(moments[-1].isoformat())
    if first == last:
        return first
    return f"{first} a {last[len(day_label(moments[-1])) + 2:]}" if moments[0].date() == moments[-1].date() else f"{first} a {last}"


def _site(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return host, f"{parts.scheme}://{parts.netloc}"


def _provenance(manifest: dict, sources: list[dict], inec_names: list[str]) -> list[dict]:
    by_id = {source["id_fuente"]: source for source in sources}
    licences = manifest.get("licencias", {})
    files: dict[str, list[dict]] = defaultdict(list)
    for query in manifest.get("consultas", []):
        parts = query["archivo"].split("/")
        if parts[1] != "news":
            files[parts[1]].append(query)
        elif parts[2] == "gdelt":
            files["gdelt"].append(query)
        else:
            files["oficiales" if by_id.get(parts[2], {}).get("tipo") == "oficial" else parts[2]].append(query)
    rows = []
    for source in sources:
        if source["tipo"] == "medio" and files.get(source["id_fuente"]):
            rows.append({"name": source["medio"], "url": source["canales"][0]["url"], "queries": files[source["id_fuente"]],
                         "text": f"{re.sub(r'^www[.]', '', source['dominio'])} · {_kind(source['canales'])}",
                         "licence": _licence(licences[f"noticias/{source['id_fuente']}"], head=source["licencia"])})
    official = [source for source in sources if source["tipo"] == "oficial"]
    if official and files.get("oficiales"):
        names = _join_spanish([OFFICIAL_ACRONYMS.get(source["id_fuente"], source["id_fuente"].upper()) for source in official])
        common = Counter(licences[f"noticias/{source['id_fuente']}"] for source in official).most_common(1)[0][0]
        rows.append({"name": "Comunicados oficiales", "url": official[0]["canales"][0]["url"], "text": f"{names} · API de WordPress",
                     "queries": files["oficiales"], "licence": _licence(common)})
    doc = next((query for query in files.get("gdelt", []) if "/doc/" in query["archivo"]), None)
    media = [source for source in sources if source["tipo"] == "medio"]
    if doc and media:
        domain = ".".join(_site(doc["url"])[0].split(".")[-2:])
        rows.append({"name": "GDELT", "url": doc["url"].split("?")[0], "text": f"{domain} · DOC y GKG", "queries": files["gdelt"],
                     "licence": _licence(licences[f"noticias/{media[0]['id_fuente']}"], gdelt=True)})
    if files.get("worldbank"):
        host, origin = _site(files["worldbank"][0]["url"])
        version = urlsplit(files["worldbank"][0]["url"]).path.split("/")[1]
        rows.append({"name": "Banco Mundial", "url": f"{origin}/{version}/", "text": f"{host} · {len(files['worldbank'])} indicadores",
                     "queries": files["worldbank"], "licence": _licence(licences["banco_mundial"])})
    if files.get("inec"):
        host, origin = _site(files["inec"][0]["url"])
        prefixes = list(dict.fromkeys(name.split("_")[0] for name in inec_names))
        rows.append({"name": "INEC", "url": f"{origin}/", "text": f"{re.sub(r'^www[.]', '', host)} · {_join_spanish([INEC_SERIES.get(p, p.upper()) for p in prefixes])}" if prefixes else re.sub(r"^www[.]", "", host),
                     "queries": files["inec"], "licence": _licence(licences["inec"])})
    if files.get("usgs"):
        rows.append({"name": "USGS", "url": files["usgs"][0]["url"].split("?")[0].rsplit("/", 1)[0] + "/",
                     "text": f"{_site(files['usgs'][0]['url'])[0]} · catálogo de sismos", "queries": files["usgs"],
                     "licence": _licence(licences["usgs"])})
    return [{"name": row["name"], "url": row["url"], "text": row["text"], "files": len(row["queries"]),
             "when": _download_times([query["fecha_descarga"] for query in row["queries"]]), "licence": row["licence"]} for row in rows]


def _hashes(manifest: dict) -> list[dict]:
    counts = manifest.get("cantidades", {})
    names = [*counts, *sorted(name for name in manifest.get("sha256", {}) if name not in counts)]
    return [{"name": name.removeprefix("processed/"), "count": counts.get(name), "sha256": manifest["sha256"][name]}
            for name in names if name in manifest.get("sha256", {})]


def _steps(manifest: dict) -> list[dict]:
    steps = []
    for text in manifest.get("transformaciones", []):
        title, _, rest = text.partition(": ")
        steps.append({"title": title, "text": rest[:1].upper() + re.sub(r" \(D-\d+\)", "", rest)[1:]})
    return steps


def quality_view(directory: Path) -> dict:
    """Everything /quality shows, derived from the quality reports, fuentes.json and the manifest."""
    reports = quality_report(directory)
    sources_path = directory / "fuentes.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))["fuentes"] if sources_path.exists() else []
    news, manifest = _loaded(reports["calidad_noticias.json"]), _loaded(reports["manifest"])
    return {
        "news": _news_section(news, sources, directory) if news else None,
        "official": _official_section(reports, directory),
        "snapshot": {"cutoff": stamp(manifest["fecha_corte_UTC"]), "version": manifest["version"],
                     "downloads": len(manifest.get("consultas", []))} if manifest else None,
        "provenance": _provenance(manifest, sources, list((_loaded(reports["calidad_inec.json"]) or {}).get("series", {}))) if manifest and sources else [],
        "steps": _steps(manifest) if manifest else [],
        "hashes": _hashes(manifest) if manifest else [],
        "integrity": manifest["integrity"] if manifest else None,
    }


# ------------------------------------------------------------- methodology

COMPONENTS = {
    "R": ("Relevancia", "Relación con Panamá y con los temas de la modalidad."),
    "I": ("Impacto potencial", "Interés público o alcance sectorial, justificado con datos; no con sensacionalismo."),
    "U": ("Urgencia", "Tiempo disponible para revisar una información o un evento."),
    "N": ("Novedad", "Diferencia frente a eventos ya agrupados; la duplicación no aumenta el puntaje."),
    "E": ("Evidencia disponible", "Fuentes pertinentes, primarias y con procedencia identificable."),
}


def score_components() -> list[dict]:
    """Component key, name and weight in contract order, for every score breakdown."""
    return [{"key": key, "name": COMPONENTS[key][0], "weight": weight} for key, weight in SCORE_WEIGHTS.items()]


EVIDENCE_NAMES = {"suficiente_para_borrador": "Suficiente para borrador", "parcial": "Evidencia parcial", "insuficiente": "Evidencia insuficiente"}


def _example(group: dict) -> dict:
    score = group["puntaje"]
    rows = [{"key": key, "name": COMPONENTS[key][0], "value": fixed(score["componentes"][key]), "weight": weight,
             "points": fixed(score["componentes"][key] * weight), "width": f"{score['componentes'][key] * weight:g}%",
             "why": spanish_decimals(score["justificaciones"][key])} for key, weight in SCORE_WEIGHTS.items()]
    return {"title": group["titulo"], "range": score["rango"], "total": fixed(score["valor"]),
            "evidence_state": group["estado_evidencia"], "evidence": EVIDENCE_NAMES[group["estado_evidencia"]],
            "rules": score["version_reglas"], "rows": rows}


def _picker(groups: list[dict], chosen: dict | None, query: str, limit: int) -> list[dict]:
    """The example picker: the best matches for the search, plus the open topic so the select always shows it."""
    needle = query.casefold()
    matches = [group for group in groups if needle in group["titulo"].casefold()][:limit]
    if chosen is not None and chosen not in matches:
        matches.append(chosen)
    return [{"id": group["id_grupo"], "label": f"{fixed(group['puntaje']['valor'])} · {group['titulo']}",
             "selected": group is chosen} for group in matches]


def methodology_view(groups: list[dict], selected: str | None = None, query: str = "", limit: int = 25) -> dict:
    """Formula, weights and ranges from the contract; the worked example from a real group."""
    needle = query.strip().casefold()
    matching = [group for group in groups if needle in group["titulo"].casefold()]
    chosen = next((group for group in groups if group["id_grupo"] == selected), matching[0] if matching else groups[0] if groups else None)
    bounds = [lo for _, lo, _ in SCORE_RANGES] + [SCORE_RANGES[-1][2]]
    return {
        "weights": [{"key": key, "name": COMPONENTS[key][0], "what": COMPONENTS[key][1], "weight": weight}
                    for key, weight in SCORE_WEIGHTS.items()],
        "formula_label": "P igual a " + " más ".join(f"{weight} {key}" for key, weight in SCORE_WEIGHTS.items()),
        "ranges": [{"name": name, "label": name.capitalize(), "size": hi - lo} for name, lo, hi in SCORE_RANGES],
        "bounds": bounds,
        "ranges_text": ". ".join(f"{name.capitalize()}: de {lo} a {'menos de ' + str(hi) if hi != SCORE_RANGES[-1][2] else str(hi)}"
                                  for name, lo, hi in SCORE_RANGES) + ".",
        "rules_version": RULES_VERSION,
        "options": _picker(groups, chosen, needle, limit),
        "no_matches": bool(needle) and not matching,
        "example": _example(chosen) if chosen else None,
    }
