"""Synthetic set that satisfies the pipeline contract, so the frontend (G6) and the API (G5) can start
before the real pipeline (G3, G4) exists. Same files and schemas as the real outputs.

The news are invented and marked `sintetico`; their URLs use the reserved `.invalid` domain. The official
figures (World Bank, INEC, USGS) are the real ones from `data/processed/`, with their real period and unit.
No model is called: every text here is written by hand, so it says nothing about the quality of the real pipeline.
"""

import csv
import hashlib
import json
from pathlib import Path

from whoami.contracts import DEMO, EVENTS_GEOJSON, HEADLINE_ONLY_LEGEND, INDICATORS_CSV, INEC_CSV
from whoami.schemas import (
    Answer,
    CaseFile,
    Citation,
    Claim,
    Components,
    ContextLink,
    Contradiction,
    ContradictionVersion,
    EditorialPackage,
    Evidence,
    Group,
    Member,
    OutputSet,
    ReviewRecord,
    Score,
    parse_utc,
    sort_inbox,
)
from whoami.store import load, write

REVIEWER = "Revisor de demostración"


def _spanish_number(value: float, decimals: int = 2) -> str:
    """Spanish decimal comma, the way a headline writes a figure."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _news_id(key: str) -> str:
    return "N-" + hashlib.sha1(f"demo:{key}".encode()).hexdigest()[:12]


def _news_item(
    key: str,
    medium: str,
    provenance: str,
    title: str,
    description: str | None,
    published: str,
    republished: str | None = None,
) -> tuple[Evidence, Member]:
    """A synthetic news item as evidence and as group member."""
    fields = {"titulo": title} | ({"descripcion": description} if description else {})
    news_id = _news_id(key)
    url = f"https://demo.invalid/{key}"
    evidence = Evidence(
        id_evidencia=news_id, tipo="noticia", titulo=title, url=url, fecha=parse_utc(published), campos=fields
    )
    member = Member(
        id_noticia=news_id,
        titulo=title,
        url=url,
        medio=medium,
        procedencia=provenance,
        fecha_publicacion=parse_utc(published),
        alcance_texto="titular_descripcion" if description else "titular_metadatos",
        recirculada_en=parse_utc(republished) if republished else None,
    )
    return evidence, member


def _csv_row(path: Path, **keys: str | int) -> dict[str, str]:
    with path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if all(row[name] == str(value) for name, value in keys.items()):
                return row
    raise LookupError(f"{path.name}: no hay fila con {keys}")


def _indicator(country: str, indicator: str, year: int, label: str, reason: str) -> tuple[Evidence, ContextLink]:
    row = _csv_row(INDICATORS_CSV, pais_iso3=country, indicador_id=indicator, anio=year)
    evidence_id = f"WB-{country}-{indicator}-{year}"
    fields = {
        "indicador": label,
        "periodo": str(year),
        "valor": _spanish_number(float(row["valor"])),
        "unidad": row["unidad"],
    }
    evidence = Evidence(
        id_evidencia=evidence_id,
        tipo="indicador",
        titulo=f"{label} ({country}, {year})",
        url=row["fuente_url"],
        fecha=None,
        campos=fields,
    )
    link = ContextLink(
        id_evidencia=evidence_id,
        etiqueta=label,
        pais=country,
        limitaciones="Serie anual del Banco Mundial: describe el año indicado, no la situación de hoy.",
        razon=reason,
    )
    return evidence, link


def _inec_point(series_id: str, period: str, label: str, reason: str) -> tuple[Evidence, ContextLink]:
    row = _csv_row(INEC_CSV, serie_id=series_id, periodo=period)
    evidence_id = f"INEC-{series_id}-{period}"
    fields = {
        "serie": row["serie"],
        "periodo": period,
        "valor": _spanish_number(float(row["valor"])),
        "unidad": row["unidad"],
        "base": row["base"],
    }
    evidence = Evidence(
        id_evidencia=evidence_id, tipo="serie_inec", titulo=label, url=row["fuente_url"], fecha=None, campos=fields
    )
    link = ContextLink(
        id_evidencia=evidence_id,
        etiqueta=label,
        pais="PAN",
        limitaciones=f"Dato mensual del INEC con base {row['base']}; puede revisarse en publicaciones posteriores.",
        razon=reason,
    )
    return evidence, link


def _quake(usgs_id: str, reason: str) -> tuple[Evidence, ContextLink]:
    with EVENTS_GEOJSON.open(encoding="utf-8") as file:
        props = next(f["properties"] for f in json.load(file)["features"] if f["properties"]["id"] == usgs_id)
    fields = {
        "lugar": props["place"],
        "periodo": props["time"][:10],
        "valor": _spanish_number(props["magnitude"], 1),
        "unidad": "magnitud",
        "hora_utc": props["time"],
        "estado": props["status"],
    }
    evidence = Evidence(
        id_evidencia=f"USGS-{usgs_id}",
        tipo="sismo",
        titulo=f"Sismo {props['place']}",
        url=props["url"],
        fecha=parse_utc(props["time"]),
        campos=fields,
    )
    link = ContextLink(
        id_evidencia=evidence.id_evidencia,
        etiqueta=f"Sismo M{fields['valor']}",
        pais="PAN",
        limitaciones="El catálogo USGS confirma el sismo (hora, magnitud, lugar); no mide daños, pérdidas ni afectados.",
        razon=reason,
    )
    return evidence, link


def _cite(evidence_id: str, field: str, passage: str) -> Citation:
    return Citation(id_evidencia=evidence_id, campo=field, pasaje=passage)


def _score(r: float, i: float, u: float, n: float, e: float, /, **why: str) -> Score:
    return Score.from_components(Components(R=r, I=i, U=u, N=n, E=e), why)


def _case_file(group: Group, scope: str, claims: list[Claim], **fields) -> CaseFile:
    return CaseFile(
        id_caso=str(group.id_caso), id_grupo=group.id_grupo, alcance_texto=scope, afirmaciones=tuple(claims), sintetico=True, **fields
    )


def build() -> OutputSet:
    evidences: dict[str, Evidence] = {}
    groups: list[Group] = []
    case_files: list[CaseFile] = []

    def register(*items: Evidence) -> None:
        evidences.update({e.id_evidencia: e for e in items})

    # ------------------------------------------------------------------ G-001 Canal: one agency republished
    acp, acp_member = _news_item(
        "canal-acp",
        "Autoridad del Canal de Panamá",
        "Autoridad del Canal de Panamá",
        "El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún",
        "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios a partir del 12 de octubre.",
        "2026-10-05T14:00:00Z",
    )
    wire = [
        _news_item(
            f"canal-efe-{medium.lower().replace(' ', '')}",
            medium,
            "EFE",
            f"El Canal de Panamá limitará los tránsitos diarios por la sequía ({medium})",
            "El Canal de Panamá reducirá los tránsitos diarios de buques por la falta de lluvias, informó la autoridad.",
            published,
        )
        for medium, published in [
            ("TVN", "2026-10-05T17:10:00Z"),
            ("Telemetro", "2026-10-05T17:45:00Z"),
            ("La Prensa", "2026-10-06T01:05:00Z"),
        ]
    ]
    exports, exports_link = _indicator(
        "PAN", "NE.EXP.GNFS.ZS", 2024, "Exportaciones de bienes y servicios",
        "El Canal es el principal exportador de servicios logísticos del país.",
    )
    register(acp, *(evidence for evidence, _ in wire), exports)
    canal = Group(
        id_grupo="G-001",
        titulo="El Canal reduce los tránsitos diarios por la sequía",
        tema="logistica_canal",
        miembros=(acp_member, *(member for _, member in wire)),
        puntaje=_score(
            1.0, 0.75, 1.0, 1.0, 1.0,
            R="Afecta directamente la operación del Canal.",
            I="Alcance sectorial: comercio y logística.",
            U="Publicado hace menos de 48 h.",
            N="Evento distinto; las réplicas de agencia no suman.",
            E="Dos procedencias distintas: el comunicado del Canal y EFE.",
        ),
        estado_evidencia="suficiente_para_borrador",
        contexto=(exports_link,),
        sin_contexto_motivo=None,
        id_caso="CASO-001",
        sintetico=True,
    )
    groups.append(canal)
    acp_cite = _cite(acp.id_evidencia, "descripcion", "limitará a 32 los tránsitos diarios")
    case_files.append(
        _case_file(
            canal,
            "titular_descripcion",
            [
                Claim(
                    id_afirmacion="A-1",
                    texto="La Autoridad del Canal informó que limitará a 32 los tránsitos diarios desde el 12 de octubre.",
                    tipo="hecho",
                    citas=(acp_cite,),
                ),
                Claim(
                    id_afirmacion="A-2",
                    texto="El motivo que señala el comunicado es el bajo nivel del lago Gatún.",
                    tipo="hecho",
                    citas=(_cite(acp.id_evidencia, "titulo", "bajo nivel del lago Gatún"),),
                ),
                Claim(
                    id_afirmacion="A-3",
                    texto="Tres medios publican la misma nota de la agencia EFE: cuentan como una sola procedencia.",
                    tipo="hecho",
                    citas=(_cite(wire[0][0].id_evidencia, "titulo", "limitará los tránsitos diarios por la sequía"),),
                ),
                Claim(
                    id_afirmacion="A-4",
                    texto="Las exportaciones de bienes y servicios fueron 44,36 % del PIB en 2024 (dato anual).",
                    tipo="hecho",
                    citas=(_cite(exports.id_evidencia, "valor", "44,36"),),
                ),
                Claim(
                    id_afirmacion="A-5",
                    texto="Una reducción de tránsitos podría afectar los ingresos por servicios logísticos.",
                    tipo="inferencia",
                    citas=(acp_cite,),
                ),
            ],
            borrador=EditorialPackage(
                titulo="El Canal reduce a 32 los tránsitos diarios por la sequía",
                brief=(
                    "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios desde el 12 de octubre "
                    "por el bajo nivel del lago Gatún. Tres medios replican la misma nota de EFE; el comunicado del Canal es "
                    "la fuente primaria. Como contexto, las exportaciones de bienes y servicios fueron 44,36 % del PIB en 2024 "
                    "(dato anual, no actual)."
                ),
                enfoque_interes_publico="Efecto de la restricción sobre el comercio marítimo y los costos logísticos.",
                preguntas=(
                    "¿Cuánto tiempo durará la restricción?",
                    "¿Qué navieras y rutas se ven más afectadas?",
                    "¿Qué medidas tomará el Canal si el nivel del lago no se recupera?",
                ),
                fuentes_y_verificaciones=(
                    "Confirmar la cifra de 32 tránsitos con el comunicado completo del Canal.",
                    "Pedir al Canal el estimado de ingresos afectados: no figura en las fuentes.",
                ),
                guion="El Canal de Panamá limitará a 32 los tránsitos diarios desde el 12 de octubre por el bajo nivel del lago Gatún.",
                copy_digital="El Canal limitará a 32 los tránsitos diarios desde el 12 de octubre por el bajo nivel del lago Gatún.",
                leyenda=None,
            ),
            vacios=("No hay estimado oficial de los ingresos afectados.",),
            contradicciones=(),
            accion_recomendada="Confirmar la cifra con el comunicado completo y pedir al Canal el impacto en ingresos.",
        )
    )

    # ------------------------------------------------------------------ G-002 Inflation: two figures that clash
    tvn_ipc, tvn_member = _news_item(
        "ipc-tvn", "TVN", "TVN", "La inflación anual en Panamá fue de 1,1 % en septiembre",
        "Analistas citan una inflación anual de 1,1 % en septiembre.", "2026-10-06T13:00:00Z",
    )
    ml_ipc, ml_member = _news_item(
        "ipc-metrolibre", "Metro Libre", "Metro Libre", "La inflación llega a 2,3 % en septiembre",
        "Un informe privado ubica la inflación anual en 2,3 % en septiembre.", "2026-10-06T15:30:00Z",
    )
    ipc_inec, ipc_inec_link = _inec_point(
        "ipc_var_interanual", "2026-08", "IPC, variación interanual (nacional urbano)",
        "Serie oficial del INEC sobre precios al consumidor.",
    )
    ipc_wb, ipc_wb_link = _indicator(
        "PAN", "FP.CPI.TOTL.ZG", 2024, "Inflación, precios al consumidor", "Referencia anual del Banco Mundial sobre inflación.",
    )
    register(tvn_ipc, ml_ipc, ipc_inec, ipc_wb)
    inflation = Group(
        id_grupo="G-002",
        titulo="Dos cifras distintas de inflación en septiembre",
        tema="economia",
        miembros=(tvn_member, ml_member),
        puntaje=_score(
            0.75, 0.75, 0.75, 1.0, 0.5,
            R="Tema económico central para Panamá.",
            I="Afecta a hogares y empresas.",
            U="Publicado ayer.",
            N="Evento distinto.",
            E="Dos procedencias, pero sin fuente oficial del mes citado.",
        ),
        estado_evidencia="parcial",
        contexto=(ipc_inec_link, ipc_wb_link),
        sin_contexto_motivo=None,
        id_caso="CASO-002",
        sintetico=True,
    )
    groups.append(inflation)
    inec_value = ipc_inec.campos["valor"]
    wb_value = ipc_wb.campos["valor"]
    case_files.append(
        _case_file(
            inflation,
            "titular_descripcion",
            [
                Claim(
                    id_afirmacion="A-1",
                    texto="TVN reporta una inflación anual de 1,1 % en septiembre, citando a analistas.",
                    tipo="declaracion",
                    citas=(_cite(tvn_ipc.id_evidencia, "descripcion", "inflación anual de 1,1 % en septiembre"),),
                    atribuida_a="analistas citados por TVN",
                ),
                Claim(
                    id_afirmacion="A-2",
                    texto="Metro Libre reporta una inflación anual de 2,3 % en septiembre, según un informe privado.",
                    tipo="declaracion",
                    citas=(_cite(ml_ipc.id_evidencia, "descripcion", "inflación anual en 2,3 % en septiembre"),),
                    atribuida_a="informe privado citado por Metro Libre",
                ),
                Claim(
                    id_afirmacion="A-3",
                    texto=f"La última variación interanual del IPC publicada por el INEC es de {inec_value} % (agosto de 2026).",
                    tipo="hecho",
                    citas=(_cite(ipc_inec.id_evidencia, "valor", inec_value),),
                ),
                Claim(
                    id_afirmacion="A-4",
                    texto=f"El Banco Mundial registra una inflación de {wb_value} % para 2024 (dato anual histórico).",
                    tipo="hecho",
                    citas=(_cite(ipc_wb.id_evidencia, "valor", wb_value),),
                ),
            ],
            borrador=EditorialPackage(
                titulo="Dos cifras de inflación para septiembre: qué se sabe y qué falta",
                brief=(
                    "Dos medios reportan cifras distintas de inflación anual para septiembre: 1,1 % (TVN, citando analistas) "
                    f"y 2,3 % (Metro Libre, citando un informe privado). El INEC publicó {inec_value} % de variación interanual "
                    "para agosto; es otro mes, por lo que no resuelve la diferencia. Hay que esperar el dato oficial de "
                    "septiembre antes de usar cualquiera de las dos cifras."
                ),
                enfoque_interes_publico="Los hogares necesitan una cifra confiable de inflación; las cifras privadas no sustituyen la oficial.",
                preguntas=(
                    "¿Qué metodología usa cada fuente?",
                    "¿Cuándo publica el INEC el dato de septiembre?",
                    "¿Por qué difieren 1,2 puntos?",
                ),
                fuentes_y_verificaciones=(
                    "Verificar la fuente y la metodología del informe privado.",
                    "Esperar el dato oficial del INEC para septiembre.",
                ),
                guion="Hay dos cifras de inflación para septiembre: 1,1 % y 2,3 %. Aún no hay dato oficial del mes.",
                copy_digital="Dos cifras distintas de inflación para septiembre. Esperamos el dato oficial del INEC.",
                leyenda=None,
            ),
            vacios=("Falta el dato oficial del INEC para septiembre.",),
            contradicciones=(
                Contradiction(
                    descripcion="Cifras distintas de inflación anual para septiembre de 2026.",
                    versiones=(
                        ContradictionVersion(
                            valor="1,1 %",
                            alcance="inflación anual, septiembre de 2026, analistas citados por TVN",
                            id_evidencia=tvn_ipc.id_evidencia,
                        ),
                        ContradictionVersion(
                            valor="2,3 %",
                            alcance="inflación anual, septiembre de 2026, informe privado citado por Metro Libre",
                            id_evidencia=ml_ipc.id_evidencia,
                        ),
                    ),
                ),
            ),
            accion_recomendada="No publicar ninguna cifra hasta contrastar con el INEC; mostrar ambas versiones como pendientes de verificar.",
        )
    )

    # ------------------------------------------------------------------ G-003 Tourism: high priority, insufficient evidence
    tourism_news, tourism_member = _news_item(
        "turismo-tvn", "TVN", "TVN", "Panamá recibe más turistas en octubre, según operadores", None, "2026-10-06T20:00:00Z"
    )
    register(tourism_news)
    tourism = Group(
        id_grupo="G-003",
        titulo="Operadores dicen que llegan más turistas en octubre",
        tema="turismo",
        miembros=(tourism_member,),
        puntaje=_score(
            0.75, 0.5, 1.0, 1.0, 0.0,
            R="Turismo es un tema prioritario.",
            I="Alcance sectorial sin cifras que lo respalden.",
            U="Publicado hace menos de 24 h.",
            N="Evento distinto.",
            E="Un solo titular, sin datos oficiales.",
        ),
        estado_evidencia="insuficiente",
        contexto=(),
        sin_contexto_motivo="No hay una cifra oficial de llegadas de visitantes en el catálogo de fuentes.",
        id_caso="CASO-003",
        sintetico=True,
    )
    groups.append(tourism)
    case_files.append(
        _case_file(
            tourism,
            "titular_metadatos",
            [
                Claim(
                    id_afirmacion="A-1",
                    texto="Operadores turísticos aseguran que llegan más turistas en octubre.",
                    tipo="declaracion",
                    citas=(_cite(tourism_news.id_evidencia, "titulo", "según operadores"),),
                    atribuida_a="operadores turísticos",
                ),
            ],
            borrador=None,
            vacios=(
                "Solo se dispone del titular.",
                "No hay cifra oficial de llegadas de visitantes ni comparación con otros meses.",
            ),
            contradicciones=(),
            accion_recomendada="Pedir a la Autoridad de Turismo la cifra oficial de llegadas antes de preparar un borrador.",
        )
    )

    # ------------------------------------------------------------------ G-004 Regulation: an attributed statement
    rule_news, rule_member = _news_item(
        "reglamento-tvn", "TVN", "TVN", "Ministra de Comercio anuncia nuevo reglamento para permisos de construcción", None,
        "2026-10-06T22:15:00Z",
    )
    register(rule_news)
    regulation = Group(
        id_grupo="G-004",
        titulo="Se anuncia un nuevo reglamento de permisos de construcción",
        tema="regulacion",
        miembros=(rule_member,),
        puntaje=_score(
            0.75, 0.5, 0.5, 1.0, 0.5,
            R="Regulación con efecto en el sector construcción.",
            I="Alcance sectorial por confirmar.",
            U="Publicado hace 1 día.",
            N="Evento distinto.",
            E="Una procedencia con atribución clara.",
        ),
        estado_evidencia="parcial",
        contexto=(),
        sin_contexto_motivo="No hay indicador oficial en el catálogo que mida permisos de construcción.",
        id_caso="CASO-004",
        sintetico=True,
    )
    groups.append(regulation)
    case_files.append(
        _case_file(
            regulation,
            "titular_metadatos",
            [
                Claim(
                    id_afirmacion="A-1",
                    texto="La ministra de Comercio anunció un nuevo reglamento para permisos de construcción.",
                    tipo="declaracion",
                    citas=(_cite(rule_news.id_evidencia, "titulo", "anuncia nuevo reglamento"),),
                    atribuida_a="la ministra de Comercio",
                ),
            ],
            borrador=EditorialPackage(
                titulo="Anuncian nuevo reglamento para permisos de construcción",
                brief="La ministra de Comercio anunció un nuevo reglamento para los permisos de construcción. No se conoce su texto ni su fecha de vigencia.",
                enfoque_interes_publico="Cambios en los trámites que afectan a constructores y compradores de vivienda.",
                preguntas=("¿Cuándo entra en vigencia?", "¿Qué trámites cambian?", "¿Qué dice el sector construcción?"),
                fuentes_y_verificaciones=("Obtener el texto del reglamento.", "Pedir la reacción del sector."),
                guion="La ministra de Comercio anunció un nuevo reglamento para permisos de construcción.",
                copy_digital="Anuncian un nuevo reglamento de permisos de construcción. Aún no se conoce su texto.",
                leyenda=HEADLINE_ONLY_LEGEND,
            ),
            vacios=("No se conoce el texto del reglamento ni su vigencia.",),
            contradicciones=(),
            accion_recomendada="Obtener el texto del reglamento antes de explicar sus efectos.",
        )
    )

    # ------------------------------------------------------------------ G-005 Public services: a notice with a date
    water_a, water_a_member = _news_item(
        "agua-tvn", "TVN", "IDAAN", "Corte programado de agua en San Miguelito el 9 de octubre",
        "El IDAAN anunció un corte programado de agua el 9 de octubre, de 8:00 a. m. a 4:00 p. m., por trabajos en la planta.",
        "2026-10-06T18:00:00Z",
    )
    water_b, water_b_member = _news_item(
        "agua-telemetro", "Telemetro", "IDAAN", "IDAAN suspenderá el servicio de agua en San Miguelito",
        "El IDAAN suspenderá el servicio el 9 de octubre por trabajos en la planta potabilizadora.", "2026-10-06T19:20:00Z",
    )
    register(water_a, water_b)
    water = Group(
        id_grupo="G-005",
        titulo="Corte programado de agua en San Miguelito",
        tema="servicios_publicos",
        miembros=(water_a_member, water_b_member),
        puntaje=_score(
            0.5, 0.5, 1.0, 1.0, 0.5,
            R="Servicio público local.",
            I="Afecta a un distrito.",
            U="El aviso vence el 9 de octubre.",
            N="Evento distinto.",
            E="Una sola procedencia, el IDAAN, repetida por dos medios.",
        ),
        estado_evidencia="suficiente_para_borrador",
        contexto=(),
        sin_contexto_motivo="Aviso operativo local: no corresponde a un indicador oficial.",
        id_caso="CASO-005",
        sintetico=True,
    )
    groups.append(water)
    case_files.append(
        _case_file(
            water,
            "titular_descripcion",
            [
                Claim(
                    id_afirmacion="A-1",
                    texto="El IDAAN anunció un corte programado de agua el 9 de octubre en San Miguelito.",
                    tipo="hecho",
                    citas=(_cite(water_a.id_evidencia, "descripcion", "corte programado de agua el 9 de octubre"),),
                ),
                Claim(
                    id_afirmacion="A-2",
                    texto="El motivo son trabajos en la planta potabilizadora.",
                    tipo="hecho",
                    citas=(_cite(water_b.id_evidencia, "descripcion", "trabajos en la planta potabilizadora"),),
                ),
            ],
            borrador=EditorialPackage(
                titulo="Corte de agua en San Miguelito el 9 de octubre",
                brief="El IDAAN anunció un corte programado de agua en San Miguelito el 9 de octubre, de 8:00 a. m. a 4:00 p. m., por trabajos en la planta potabilizadora.",
                enfoque_interes_publico="Aviso útil para los hogares afectados.",
                preguntas=("¿Qué sectores quedan sin agua?", "¿Habrá camiones cisterna?", "¿A qué hora se normaliza el servicio?"),
                fuentes_y_verificaciones=("Confirmar con el IDAAN los sectores afectados.",),
                guion="El IDAAN cortará el agua en San Miguelito el 9 de octubre, de 8 de la mañana a 4 de la tarde.",
                copy_digital="Corte de agua en San Miguelito el 9 de octubre, de 8:00 a. m. a 4:00 p. m., por trabajos del IDAAN.",
                leyenda=None,
            ),
            vacios=("Faltan los sectores afectados.",),
            contradicciones=(),
            accion_recomendada="Confirmar con el IDAAN los sectores afectados y publicar el aviso con su vigencia.",
        )
    )

    # ------------------------------------------------------------------ G-006 Earthquake: an old story, recirculated
    old_news, old_member = _news_item(
        "sismo-viejo", "TVN", "TVN", "Sismo de magnitud 5,6 sacude la zona fronteriza con Costa Rica",
        "El Servicio Geológico de EE. UU. reportó el sismo frente a las costas de Burica.", "2025-12-17T23:30:00Z",
        republished="2026-10-05T18:00:00Z",
    )
    quake, quake_link = _quake("us6000rvkl", "Sismo registrado el mismo día de la publicación original.")
    register(old_news, quake)
    groups.append(
        Group(
            id_grupo="G-006",
            titulo="Sismo de magnitud 5,6 frente a Burica (noticia recirculada)",
            tema="eventos_naturales",
            miembros=(old_member,),
            puntaje=_score(
                0.5, 0.5, 0.0, 0.0, 1.0,
                R="Evento natural en la región.",
                I="Sin daños reportados.",
                U="El evento ocurrió en diciembre de 2025.",
                N="Recirculación sin cambios: no es un evento nuevo.",
                E="Confirmado por el catálogo USGS.",
            ),
            estado_evidencia="parcial",
            contexto=(quake_link,),
            sin_contexto_motivo=None,
            id_caso=None,
            sintetico=True,
        )
    )

    # ------------------------------------------------------------------ G-007 No topic: no class is forced
    other_news, other_member = _news_item(
        "concurso-tvn", "TVN", "TVN", "TVN estrena nueva temporada de su programa de concursos", None, "2026-10-04T15:00:00Z"
    )
    register(other_news)
    groups.append(
        Group(
            id_grupo="G-007",
            titulo="Estreno de temporada de un programa de concursos",
            tema="sin_tema",
            miembros=(other_member,),
            puntaje=_score(
                0.25, 0.25, 0.5, 1.0, 0.0,
                R="Sin relación con los temas del reto.",
                I="Sin interés público demostrado.",
                U="Publicado hace 3 días.",
                N="Evento distinto.",
                E="Una procedencia sin datos que lo respalden.",
            ),
            estado_evidencia="insuficiente",
            contexto=(),
            sin_contexto_motivo="Fuera de los seis temas del reto: no se forzó un vínculo ni una clase.",
            id_caso=None,
            sintetico=True,
        )
    )

    answers = (
        Answer(
            id_consulta="Q-1",
            consulta="¿Cuántos tránsitos diarios limitará el Canal?",
            estado="respondida",
            respuesta="La Autoridad del Canal informó que limitará a 32 los tránsitos diarios desde el 12 de octubre.",
            citas=(acp_cite,),
        ),
        Answer(
            id_consulta="Q-2",
            consulta="¿Cuánto representaron las exportaciones de bienes y servicios en 2024?",
            estado="respondida",
            respuesta="Representaron 44,36 % del PIB en 2024. Es un dato anual del Banco Mundial, no una medición actual.",
            citas=(_cite(exports.id_evidencia, "valor", "44,36"),),
        ),
        Answer(
            id_consulta="Q-3",
            consulta="¿Cuál es la inflación de septiembre?",
            estado="contradiccion",
            versiones=(
                ContradictionVersion(valor="1,1 %", alcance="analistas citados por TVN", id_evidencia=tvn_ipc.id_evidencia),
                ContradictionVersion(valor="2,3 %", alcance="informe privado citado por Metro Libre", id_evidencia=ml_ipc.id_evidencia),
            ),
        ),
        Answer(
            id_consulta="Q-4",
            consulta="¿Cuál será el PIB de Panamá en 2027?",
            estado="abstencion",
            motivo_abstencion="Ninguna fuente del corpus contiene una cifra de 2027.",
            faltante="Una proyección oficial del PIB de 2027 con su fuente y fecha.",
        ),
    )

    def review(case_id: str, state: str, at: str, note: str | None) -> ReviewRecord:
        return ReviewRecord(id_caso=case_id, estado=state, responsable=REVIEWER, fecha=parse_utc(at), nota=note)  # type: ignore[arg-type]

    reviews = (
        review("CASO-001", "en_revision", "2026-10-07T13:00:00Z", "Pendiente confirmar la cifra con el comunicado."),
        review("CASO-002", "en_revision", "2026-10-07T13:10:00Z", "Esperando el dato oficial del INEC."),
        review("CASO-003", "requiere_evidencia", "2026-10-07T13:20:00Z", "Solo hay un titular."),
        review("CASO-005", "en_revision", "2026-10-07T13:25:00Z", None),
        review("CASO-005", "aprobado_como_borrador", "2026-10-07T13:30:00Z", "Aviso verificado con dos medios."),
    )
    return OutputSet(
        grupos=tuple(sort_inbox(groups)),
        evidencias=evidences,
        fichas=tuple(case_files),
        consultas=answers,
        revisiones=reviews,
    )


def generate(directory: Path = DEMO) -> OutputSet:
    """Writes the synthetic set and reads it back: what the interface loads must equal what was built."""
    output = build()
    write(output, directory, directory)
    loaded = load(directory, directory)
    if loaded != output:
        raise AssertionError("los archivos de demostración no se leen igual que se escribieron")
    return loaded
