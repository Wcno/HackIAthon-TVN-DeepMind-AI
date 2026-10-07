"""Reads and writes the pipeline outputs as JSON Lines (one record per line, UTF-8)."""

import json
import types
from dataclasses import MISSING, asdict, dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from whoami.contracts import (
    DEMO,
    EVIDENCE_FILE,
    FICHAS_FILE,
    GROUPS_FILE,
    OUTPUTS,
    PROCESSED,
    QUERIES_FILE,
    REVIEWS_FILE,
)
from whoami.schemas import Evidencia, Ficha, Grupo, RegistroRevision, Respuesta, errores_de_citas


def a_dict(valor: Any) -> Any:
    return asdict(valor)


def de_dict(tipo: Any, datos: Any) -> Any:
    """Rebuilds a schema from `a_dict` output, running every construction-time invariant again."""
    origen = get_origin(tipo)
    if origen in (Union, types.UnionType):
        if datos is None:
            return None
        interior = [arg for arg in get_args(tipo) if arg is not type(None)]
        return de_dict(interior[0], datos)
    if origen is tuple:
        return tuple(de_dict(get_args(tipo)[0], item) for item in datos)
    if origen is dict:
        return dict(datos)
    if isinstance(tipo, type) and is_dataclass(tipo):
        hints = get_type_hints(tipo)
        campos = fields(tipo)
        desconocidos = set(datos) - {f.name for f in campos}
        faltan = [f.name for f in campos if f.name not in datos and f.default is MISSING and f.default_factory is MISSING]
        if desconocidos or faltan:
            raise ValueError(f"{tipo.__name__}: campos desconocidos {sorted(desconocidos)}, campos que faltan {faltan}")
        return tipo(**{f.name: de_dict(hints[f.name], datos[f.name]) for f in campos if f.name in datos})
    return datos


def a_registro_ficha(ficha: Ficha) -> dict:
    """§7 `fichas.jsonl` record: the minimum fields first, in the order the challenge lists them.

    `puntaje` is the number and `componentes` the five values; the rest of the score travels in
    `puntaje_detalle` and the flat `citas` list repeats the citations of the claims.
    """
    datos = a_dict(ficha)
    citas: list[dict] = []
    for afirmacion in datos["afirmaciones"]:
        for cita in afirmacion["citas"]:
            if cita not in citas:
                citas.append(cita)
    puntaje = datos.pop("puntaje")
    registro = {
        "id_caso": datos.pop("id_caso"),
        "modalidad": datos.pop("modalidad"),
        "ids_fuente": datos.pop("ids_fuente"),
        "afirmaciones": datos.pop("afirmaciones"),
        "citas": citas,
        "puntaje": puntaje["valor"],
        "componentes": puntaje["componentes"],
        "estado_evidencia": datos.pop("estado_evidencia"),
        "borrador": datos.pop("borrador"),
        "estado_revision": datos.pop("estado_revision"),
    }
    registro["puntaje_detalle"] = {k: puntaje[k] for k in ("rango", "version_reglas", "justificaciones")}
    return registro | datos


def de_registro_ficha(registro: dict) -> Ficha:
    datos = {k: v for k, v in registro.items() if k not in ("citas", "puntaje", "componentes", "puntaje_detalle")}
    datos["puntaje"] = {
        "componentes": registro["componentes"],
        "valor": registro["puntaje"],
        **registro["puntaje_detalle"],
    }
    return de_dict(Ficha, datos)


def escribir_jsonl(ruta: Path, registros: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for registro in registros:
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def leer_jsonl(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8") as archivo:
        return [json.loads(linea) for linea in archivo if linea.strip()]


@dataclass(frozen=True)
class Paquete:
    """Everything the interface and the API read, as one validated object."""

    grupos: tuple[Grupo, ...]
    evidencias: dict[str, Evidencia]
    fichas: tuple[Ficha, ...]
    consultas: tuple[Respuesta, ...]
    revisiones: tuple[RegistroRevision, ...]


def verificar(paquete: Paquete) -> None:
    """Rules that span records, which no single schema can see. Raises with every problem found."""
    problemas = []
    citas = [c for f in paquete.fichas for a in f.afirmaciones for c in a.citas]
    citas += [c for q in paquete.consultas for c in q.citas]
    problemas += errores_de_citas(citas, paquete.evidencias)
    versiones = [v for f in paquete.fichas for c in f.contradicciones for v in c.versiones]
    versiones += [v for q in paquete.consultas for v in q.versiones]
    problemas += [
        f"{v.id_evidencia}: la versión contradictoria cita una evidencia que no existe"
        for v in versiones
        if v.id_evidencia not in paquete.evidencias
    ]
    for grupo in paquete.grupos:
        ids = [m.id_noticia for m in grupo.miembros] + [v.id_evidencia for v in grupo.contexto]
        problemas += [f"{grupo.id_grupo}: {i} no está en evidencias" for i in ids if i not in paquete.evidencias]
    casos = {f.id_caso: f for f in paquete.fichas}
    grupos = {g.id_grupo: g for g in paquete.grupos}
    for ficha in paquete.fichas:
        origen = grupos.get(ficha.id_grupo)
        if (
            origen is None
            or origen.id_caso != ficha.id_caso
            or origen.puntaje != ficha.puntaje
            or origen.estado_revision != ficha.estado_revision
        ):
            problemas.append(f"{ficha.id_caso}: la ficha no coincide con su grupo")
    problemas += [
        f"{g.id_grupo}: id_caso {g.id_caso} sin ficha" for g in paquete.grupos if g.id_caso and g.id_caso not in casos
    ]
    ultimo: dict[str, str] = {}
    for revision in paquete.revisiones:
        ultimo[revision.id_caso] = revision.estado
    for id_caso, estado in ultimo.items():
        if id_caso not in casos:
            problemas.append(f"{id_caso}: hay revisiones de un caso sin ficha")
        elif casos[id_caso].estado_revision != estado:
            problemas.append(f"{id_caso}: la revisión más reciente ({estado}) no coincide con la ficha")
    if problemas:
        raise ValueError("el paquete es incoherente:\n- " + "\n- ".join(problemas))


def escribir(paquete: Paquete, datos: Path = PROCESSED, salidas: Path = OUTPUTS) -> None:
    """Validates the whole package, then writes `grupos` and `evidencias` to `datos` and the rest to `salidas`."""
    verificar(paquete)
    escribir_jsonl(datos / GROUPS_FILE, [a_dict(g) for g in paquete.grupos])
    escribir_jsonl(datos / EVIDENCE_FILE, [a_dict(e) for e in paquete.evidencias.values()])
    escribir_jsonl(salidas / FICHAS_FILE, [a_registro_ficha(f) for f in paquete.fichas])
    escribir_jsonl(salidas / QUERIES_FILE, [a_dict(c) for c in paquete.consultas])
    escribir_jsonl(salidas / REVIEWS_FILE, [a_dict(r) for r in paquete.revisiones])


def cargar(datos: Path = PROCESSED, salidas: Path = OUTPUTS) -> Paquete:
    """Loads the real pipeline output, rejecting anything that breaks a schema or a cross-record rule."""
    evidencias = [de_dict(Evidencia, r) for r in leer_jsonl(datos / EVIDENCE_FILE)]
    paquete = Paquete(
        grupos=tuple(de_dict(Grupo, r) for r in leer_jsonl(datos / GROUPS_FILE)),
        evidencias={e.id_evidencia: e for e in evidencias},
        fichas=tuple(de_registro_ficha(r) for r in leer_jsonl(salidas / FICHAS_FILE)),
        consultas=tuple(de_dict(Respuesta, r) for r in leer_jsonl(salidas / QUERIES_FILE)),
        revisiones=tuple(de_dict(RegistroRevision, r) for r in leer_jsonl(salidas / REVIEWS_FILE)),
    )
    verificar(paquete)
    return paquete


def cargar_demo() -> Paquete:
    """The synthetic set in `data/demo/`: same files and schemas, all in one directory."""
    return cargar(DEMO, DEMO)
