"""Synthetic set that satisfies the pipeline contract, so the frontend (G6) and the API (G5) can start
before the real pipeline (G3, G4) exists. Same files and schemas as the real outputs.

The news are invented and marked `sintetico`; their URLs use the reserved `.invalid` domain. The official
figures (World Bank, INEC, USGS) are the real ones from `data/processed/`, with their real period and unit.
"""

import csv
import hashlib
import json

from whoami.contracts import DEMO, EVENTS_GEOJSON, HEADLINE_ONLY_LEGEND, INDICATORS_CSV, INEC_CSV
from whoami.schemas import (
    Afirmacion,
    Cita,
    Componentes,
    Contradiccion,
    Evidencia,
    Ficha,
    Grupo,
    Miembro,
    PaqueteEditorial,
    Puntaje,
    RegistroRevision,
    Respuesta,
    VersionContradictoria,
    VinculoContexto,
    ordenar_bandeja,
)
from whoami.store import Paquete, cargar, escribir

DEMO_REVIEWER = "Revisor de demostración"
SYNTHETIC_NOTICE = "Noticia sintética de demostración."


def _es(valor: float, decimales: int = 2) -> str:
    """Spanish decimal comma, the way a headline writes a figure."""
    return f"{valor:.{decimales}f}".replace(".", ",")


def _news_id(clave: str) -> str:
    return "N-" + hashlib.sha1(f"demo:{clave}".encode()).hexdigest()[:12]


def _noticia(clave: str, medio: str, procedencia: str, titulo: str, descripcion: str | None, fecha: str, **extra):
    """A synthetic news item as evidence and as group member."""
    campos = {"titulo": titulo} | ({"descripcion": descripcion} if descripcion else {})
    id_noticia = _news_id(clave)
    evidencia = Evidencia(id_noticia, "noticia", titulo, f"https://demo.invalid/{clave}", fecha, campos)
    miembro = Miembro(
        id_noticia=id_noticia,
        titulo=titulo,
        url=evidencia.url,
        medio=medio,
        procedencia=procedencia,
        fecha_publicacion=fecha,
        alcance_texto="titular_descripcion" if descripcion else "titular_metadatos",
        recirculada_en=extra.get("recirculada_en"),
    )
    return evidencia, miembro


def _csv_row(ruta, **claves) -> dict:
    with ruta.open(encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            if all(fila[k] == str(v) for k, v in claves.items()):
                return fila
    raise LookupError(f"{ruta.name}: no hay fila con {claves}")


def _indicador(pais: str, indicador: str, anio: int, etiqueta: str, razon: str):
    fila = _csv_row(INDICATORS_CSV, pais_iso3=pais, indicador_id=indicador, anio=anio)
    valor = float(fila["valor"])
    id_evidencia = f"WB-{pais}-{indicador}-{anio}"
    campos = {"indicador": etiqueta, "periodo": str(anio), "valor": _es(valor), "unidad": fila["unidad"]}
    evidencia = Evidencia(id_evidencia, "indicador", f"{etiqueta} ({pais}, {anio})", fila["fuente_url"], None, campos)
    vinculo = VinculoContexto(
        id_evidencia, etiqueta, pais, str(anio), valor, fila["unidad"],
        "Serie anual del Banco Mundial: describe el año indicado, no la situación de hoy.", razon,
    )
    return evidencia, vinculo


def _inec(serie_id: str, periodo: str, etiqueta: str, razon: str):
    fila = _csv_row(INEC_CSV, serie_id=serie_id, periodo=periodo)
    valor = float(fila["valor"])
    id_evidencia = f"INEC-{serie_id}-{periodo}"
    campos = {"serie": fila["serie"], "periodo": periodo, "valor": _es(valor), "unidad": fila["unidad"], "base": fila["base"]}
    evidencia = Evidencia(id_evidencia, "serie_inec", etiqueta, fila["fuente_url"], None, campos)
    vinculo = VinculoContexto(
        id_evidencia, etiqueta, "PAN", periodo, valor, fila["unidad"],
        f"Dato mensual del INEC con base {fila['base']}; puede revisarse en publicaciones posteriores.", razon,
    )
    return evidencia, vinculo


def _sismo(usgs_id: str, razon: str):
    with EVENTS_GEOJSON.open(encoding="utf-8") as archivo:
        propiedades = next(f["properties"] for f in json.load(archivo)["features"] if f["properties"]["id"] == usgs_id)
    campos = {
        "lugar": propiedades["place"],
        "magnitud": _es(propiedades["magnitude"], 1),
        "hora_utc": propiedades["time"],
        "estado": propiedades["status"],
    }
    evidencia = Evidencia(f"USGS-{usgs_id}", "sismo", f"Sismo {propiedades['place']}", propiedades["url"], propiedades["time"], campos)
    vinculo = VinculoContexto(
        evidencia.id_evidencia, f"Sismo M{campos['magnitud']}", "PAN", propiedades["time"][:10], propiedades["magnitude"],
        "magnitud",
        "El catálogo USGS confirma el sismo (hora, magnitud, lugar); no mide daños, pérdidas ni afectados.", razon,
    )
    return evidencia, vinculo


def _just(**textos: str) -> dict[str, str]:
    return textos


def _ficha(grupo: Grupo, id_caso: str, alcance: str, afirmaciones, **campos) -> Ficha:
    ids = list(dict.fromkeys(cita.id_evidencia for a in afirmaciones for cita in a.citas))
    return Ficha(
        id_caso=id_caso, modalidad="editorial_tvn", id_grupo=grupo.id_grupo, titulo=grupo.titulo, tema=grupo.tema,
        alcance_texto=alcance, ids_fuente=tuple(ids), afirmaciones=tuple(afirmaciones), puntaje=grupo.puntaje,
        estado_evidencia=grupo.estado_evidencia, estado_revision=grupo.estado_revision, sintetico=True, **campos,
    )


def construir() -> Paquete:
    evidencias: dict[str, Evidencia] = {}
    grupos: list[Grupo] = []
    fichas: list[Ficha] = []

    def registrar(*items: Evidencia) -> None:
        evidencias.update({e.id_evidencia: e for e in items})

    # ------------------------------------------------------------------ G-001 Canal: una agencia replicada
    acp, m_acp = _noticia(
        "canal-acp", "Autoridad del Canal de Panamá", "Autoridad del Canal de Panamá",
        "El Canal de Panamá reduce a 32 los tránsitos diarios por el bajo nivel del lago Gatún",
        "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios a partir del 12 de octubre.",
        "2026-10-05T14:00:00Z",
    )
    efe = [
        _noticia(f"canal-efe-{medio.lower().replace(' ', '')}", medio, "EFE",
                 f"El Canal de Panamá limitará los tránsitos diarios por la sequía ({medio})",
                 "El Canal de Panamá reducirá los tránsitos diarios de buques por la falta de lluvias, informó la autoridad.",
                 fecha)
        for medio, fecha in [("TVN", "2026-10-05T17:10:00Z"), ("Telemetro", "2026-10-05T17:45:00Z"), ("La Prensa", "2026-10-06T01:05:00Z")]
    ]
    exp, v_exp = _indicador("PAN", "NE.EXP.GNFS.ZS", 2024, "Exportaciones de bienes y servicios",
                            "El Canal es el principal exportador de servicios logísticos del país.")
    registrar(acp, *(e for e, _ in efe), exp)
    g1 = Grupo(
        "G-001", "El Canal reduce los tránsitos diarios por la sequía", "logistica_canal",
        (m_acp, *(m for _, m in efe)),
        Puntaje.de(Componentes(R=1.0, I=0.75, U=1.0, N=1.0, E=1.0), _just(
            R="Afecta directamente la operación del Canal.", I="Alcance sectorial: comercio y logística.",
            U="Publicado hace menos de 48 h.", N="Evento distinto; las réplicas de agencia no suman.",
            E="Dos procedencias distintas: el comunicado del Canal y EFE.")),
        "suficiente_para_borrador", "en_revision", (v_exp,), None, "CASO-001", True,
    )
    grupos.append(g1)
    cita_acp = Cita(acp.id_evidencia, "descripcion", "limitará a 32 los tránsitos diarios")
    fichas.append(_ficha(g1, "CASO-001", "titular_descripcion", [
        Afirmacion("A-1", "La Autoridad del Canal informó que limitará a 32 los tránsitos diarios desde el 12 de octubre.", "hecho", (cita_acp,)),
        Afirmacion("A-2", "El motivo que señala el comunicado es el bajo nivel del lago Gatún.", "hecho",
                   (Cita(acp.id_evidencia, "titulo", "bajo nivel del lago Gatún"),)),
        Afirmacion("A-3", "Tres medios publican la misma nota de la agencia EFE: cuentan como una sola procedencia.", "hecho",
                   (Cita(efe[0][0].id_evidencia, "titulo", "limitará los tránsitos diarios por la sequía"),)),
        Afirmacion("A-4", "Las exportaciones de bienes y servicios fueron 44,36 % del PIB en 2024 (dato anual).", "hecho",
                   (Cita(exp.id_evidencia, "valor", "44,36"),)),
        Afirmacion("A-5", "Una reducción de tránsitos podría afectar los ingresos por servicios logísticos.", "inferencia", (cita_acp,)),
    ], borrador=PaqueteEditorial(
        titulo="El Canal reduce a 32 los tránsitos diarios por la sequía",
        brief=("La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios desde el 12 de octubre por el "
               "bajo nivel del lago Gatún. Tres medios replican la misma nota de EFE; el comunicado del Canal es la fuente primaria. "
               "Como contexto, las exportaciones de bienes y servicios fueron 44,36 % del PIB en 2024 (dato anual, no actual)."),
        enfoque_interes_publico="Efecto de la restricción sobre el comercio marítimo y los costos logísticos.",
        preguntas=("¿Cuánto tiempo durará la restricción?", "¿Qué navieras y rutas se ven más afectadas?",
                   "¿Qué medidas tomará el Canal si el nivel del lago no se recupera?"),
        fuentes_y_verificaciones=("Confirmar la cifra de 32 tránsitos con el comunicado completo del Canal.",
                                  "Pedir al Canal el estimado de ingresos afectados: no figura en las fuentes."),
        guion="El Canal de Panamá limitará a 32 los tránsitos diarios desde el 12 de octubre por el bajo nivel del lago Gatún.",
        copy_digital="El Canal limitará a 32 los tránsitos diarios desde el 12 de octubre por el bajo nivel del lago Gatún.",
        leyenda=None,
    ), vacios=("No hay estimado oficial de los ingresos afectados.",), contradicciones=(),
        accion_recomendada="Confirmar la cifra con el comunicado completo y pedir al Canal el impacto en ingresos."))

    # ------------------------------------------------------------------ G-002 Inflación: dos cifras que chocan
    tvn_ipc, m_tvn = _noticia(
        "ipc-tvn", "TVN", "TVN", "La inflación anual en Panamá fue de 1,1 % en septiembre",
        "Analistas citan una inflación anual de 1,1 % en septiembre.", "2026-10-06T13:00:00Z")
    ml_ipc, m_ml = _noticia(
        "ipc-metrolibre", "Metro Libre", "Metro Libre", "La inflación llega a 2,3 % en septiembre",
        "Un informe privado ubica la inflación anual en 2,3 % en septiembre.", "2026-10-06T15:30:00Z")
    ipc_inec, v_inec = _inec("ipc_var_interanual", "2026-08", "IPC, variación interanual (nacional urbano)",
                             "Serie oficial del INEC sobre precios al consumidor.")
    ipc_wb, v_wb = _indicador("PAN", "FP.CPI.TOTL.ZG", 2024, "Inflación, precios al consumidor",
                              "Referencia anual del Banco Mundial sobre inflación.")
    registrar(tvn_ipc, ml_ipc, ipc_inec, ipc_wb)
    g2 = Grupo(
        "G-002", "Dos cifras distintas de inflación en septiembre", "economia", (m_tvn, m_ml),
        Puntaje.de(Componentes(R=0.75, I=0.75, U=0.75, N=1.0, E=0.5), _just(
            R="Tema económico central para Panamá.", I="Afecta a hogares y empresas.", U="Publicado ayer.",
            N="Evento distinto.", E="Dos procedencias, pero sin fuente oficial del mes citado.")),
        "parcial", "en_revision", (v_inec, v_wb), None, "CASO-002", True,
    )
    grupos.append(g2)
    fichas.append(_ficha(g2, "CASO-002", "titular_descripcion", [
        Afirmacion("A-1", "TVN reporta una inflación anual de 1,1 % en septiembre, citando a analistas.", "declaracion",
                   (Cita(tvn_ipc.id_evidencia, "descripcion", "inflación anual de 1,1 % en septiembre"),), "analistas citados por TVN"),
        Afirmacion("A-2", "Metro Libre reporta una inflación anual de 2,3 % en septiembre, según un informe privado.", "declaracion",
                   (Cita(ml_ipc.id_evidencia, "descripcion", "inflación anual en 2,3 % en septiembre"),), "informe privado citado por Metro Libre"),
        Afirmacion("A-3", f"La última variación interanual del IPC publicada por el INEC es de {_es(v_inec.valor)} % (agosto de 2026).", "hecho",
                   (Cita(ipc_inec.id_evidencia, "valor", _es(v_inec.valor)),)),
        Afirmacion("A-4", f"El Banco Mundial registra una inflación de {_es(v_wb.valor)} % para 2024 (dato anual histórico).", "hecho",
                   (Cita(ipc_wb.id_evidencia, "valor", _es(v_wb.valor)),)),
    ], borrador=PaqueteEditorial(
        titulo="Dos cifras de inflación para septiembre: qué se sabe y qué falta",
        brief=("Dos medios reportan cifras distintas de inflación anual para septiembre: 1,1 % (TVN, citando analistas) y 2,3 % "
               f"(Metro Libre, citando un informe privado). El INEC publicó {_es(v_inec.valor)} % de variación interanual para agosto; "
               "es otro mes, por lo que no resuelve la diferencia. Hay que esperar el dato oficial de septiembre antes de usar cualquiera de las dos cifras."),
        enfoque_interes_publico="Los hogares necesitan una cifra confiable de inflación; las cifras privadas no sustituyen la oficial.",
        preguntas=("¿Qué metodología usa cada fuente?", "¿Cuándo publica el INEC el dato de septiembre?", "¿Por qué difieren 1,2 puntos?"),
        fuentes_y_verificaciones=("Verificar la fuente y la metodología del informe privado.", "Esperar el dato oficial del INEC para septiembre."),
        guion="Hay dos cifras de inflación para septiembre: 1,1 % y 2,3 %. Aún no hay dato oficial del mes.",
        copy_digital="Dos cifras distintas de inflación para septiembre. Esperamos el dato oficial del INEC.",
        leyenda=None,
    ), vacios=("Falta el dato oficial del INEC para septiembre.",),
        contradicciones=(Contradiccion("Cifras distintas de inflación anual para septiembre de 2026.", (
            VersionContradictoria("1,1 %", "inflación anual, septiembre de 2026, analistas citados por TVN", tvn_ipc.id_evidencia),
            VersionContradictoria("2,3 %", "inflación anual, septiembre de 2026, informe privado citado por Metro Libre", ml_ipc.id_evidencia))),),
        accion_recomendada="No publicar ninguna cifra hasta contrastar con el INEC; mostrar ambas versiones como pendientes de verificar."))

    # ------------------------------------------------------------------ G-003 Turismo: prioridad alta, evidencia insuficiente
    tur, m_tur = _noticia("turismo-tvn", "TVN", "TVN", "Panamá recibe más turistas en octubre, según operadores", None,
                          "2026-10-06T20:00:00Z")
    registrar(tur)
    g3 = Grupo(
        "G-003", "Operadores dicen que llegan más turistas en octubre", "turismo", (m_tur,),
        Puntaje.de(Componentes(R=0.75, I=0.5, U=1.0, N=1.0, E=0.0), _just(
            R="Turismo es un tema prioritario.", I="Alcance sectorial sin cifras que lo respalden.", U="Publicado hace menos de 24 h.",
            N="Evento distinto.", E="Un solo titular, sin datos oficiales.")),
        "insuficiente", "requiere_evidencia", (), "No hay una cifra oficial de llegadas de visitantes en el catálogo de fuentes.",
        "CASO-003", True,
    )
    grupos.append(g3)
    fichas.append(_ficha(g3, "CASO-003", "titular_metadatos", [
        Afirmacion("A-1", "Operadores turísticos aseguran que llegan más turistas en octubre.", "declaracion",
                   (Cita(tur.id_evidencia, "titulo", "según operadores"),), "operadores turísticos"),
    ], borrador=None, vacios=("Solo se dispone del titular.", "No hay cifra oficial de llegadas de visitantes ni comparación con otros meses."),
        contradicciones=(), accion_recomendada="Pedir a la Autoridad de Turismo la cifra oficial de llegadas antes de preparar un borrador."))

    # ------------------------------------------------------------------ G-004 Regulación: declaración atribuida
    reg, m_reg = _noticia("reglamento-tvn", "TVN", "TVN", "Ministra de Comercio anuncia nuevo reglamento para permisos de construcción",
                          None, "2026-10-06T22:15:00Z")
    registrar(reg)
    g4 = Grupo(
        "G-004", "Se anuncia un nuevo reglamento de permisos de construcción", "regulacion", (m_reg,),
        Puntaje.de(Componentes(R=0.75, I=0.5, U=0.5, N=1.0, E=0.5), _just(
            R="Regulación con efecto en el sector construcción.", I="Alcance sectorial por confirmar.", U="Publicado hace 1 día.",
            N="Evento distinto.", E="Una procedencia con atribución clara.")),
        "parcial", "nuevo", (), "No hay indicador oficial en el catálogo que mida permisos de construcción.", "CASO-004", True,
    )
    grupos.append(g4)
    fichas.append(_ficha(g4, "CASO-004", "titular_metadatos", [
        Afirmacion("A-1", "La ministra de Comercio anunció un nuevo reglamento para permisos de construcción.", "declaracion",
                   (Cita(reg.id_evidencia, "titulo", "anuncia nuevo reglamento"),), "la ministra de Comercio"),
    ], borrador=PaqueteEditorial(
        titulo="Anuncian nuevo reglamento para permisos de construcción",
        brief="La ministra de Comercio anunció un nuevo reglamento para los permisos de construcción. No se conoce su texto ni su fecha de vigencia.",
        enfoque_interes_publico="Cambios en los trámites que afectan a constructores y compradores de vivienda.",
        preguntas=("¿Cuándo entra en vigencia?", "¿Qué trámites cambian?", "¿Qué dice el sector construcción?"),
        fuentes_y_verificaciones=("Obtener el texto del reglamento.", "Pedir la reacción del sector."),
        guion="La ministra de Comercio anunció un nuevo reglamento para permisos de construcción.",
        copy_digital="Anuncian un nuevo reglamento de permisos de construcción. Aún no se conoce su texto.",
        leyenda=HEADLINE_ONLY_LEGEND,
    ), vacios=("No se conoce el texto del reglamento ni su vigencia.",), contradicciones=(),
        accion_recomendada="Obtener el texto del reglamento antes de explicar sus efectos."))

    # ------------------------------------------------------------------ G-005 Servicios públicos: aviso vigente
    agua_a, m_a = _noticia("agua-tvn", "TVN", "IDAAN", "Corte programado de agua en San Miguelito el 9 de octubre",
                           "El IDAAN anunció un corte programado de agua el 9 de octubre, de 8:00 a. m. a 4:00 p. m., por trabajos en la planta.",
                           "2026-10-06T18:00:00Z")
    agua_b, m_b = _noticia("agua-telemetro", "Telemetro", "IDAAN", "IDAAN suspenderá el servicio de agua en San Miguelito",
                           "El IDAAN suspenderá el servicio el 9 de octubre por trabajos en la planta potabilizadora.",
                           "2026-10-06T19:20:00Z")
    registrar(agua_a, agua_b)
    g5 = Grupo(
        "G-005", "Corte programado de agua en San Miguelito", "servicios_publicos", (m_a, m_b),
        Puntaje.de(Componentes(R=0.5, I=0.5, U=1.0, N=1.0, E=0.5), _just(
            R="Servicio público local.", I="Afecta a un distrito.", U="El aviso vence el 9 de octubre.",
            N="Evento distinto.", E="Una sola procedencia, el IDAAN, repetida por dos medios.")),
        "suficiente_para_borrador", "aprobado_como_borrador", (), "Aviso operativo local: no corresponde a un indicador oficial.",
        "CASO-005", True,
    )
    grupos.append(g5)
    fichas.append(_ficha(g5, "CASO-005", "titular_descripcion", [
        Afirmacion("A-1", "El IDAAN anunció un corte programado de agua el 9 de octubre en San Miguelito.", "hecho",
                   (Cita(agua_a.id_evidencia, "descripcion", "corte programado de agua el 9 de octubre"),)),
        Afirmacion("A-2", "El motivo son trabajos en la planta potabilizadora.", "hecho",
                   (Cita(agua_b.id_evidencia, "descripcion", "trabajos en la planta potabilizadora"),)),
    ], borrador=PaqueteEditorial(
        titulo="Corte de agua en San Miguelito el 9 de octubre",
        brief="El IDAAN anunció un corte programado de agua en San Miguelito el 9 de octubre, de 8:00 a. m. a 4:00 p. m., por trabajos en la planta potabilizadora.",
        enfoque_interes_publico="Aviso útil para los hogares afectados.",
        preguntas=("¿Qué sectores quedan sin agua?", "¿Habrá camiones cisterna?", "¿A qué hora se normaliza el servicio?"),
        fuentes_y_verificaciones=("Confirmar con el IDAAN los sectores afectados.",),
        guion="El IDAAN cortará el agua en San Miguelito el 9 de octubre, de 8 de la mañana a 4 de la tarde.",
        copy_digital="Corte de agua en San Miguelito el 9 de octubre, de 8:00 a. m. a 4:00 p. m., por trabajos del IDAAN.",
        leyenda=None,
    ), vacios=("Faltan los sectores afectados.",), contradicciones=(),
        accion_recomendada="Confirmar con el IDAAN los sectores afectados y publicar el aviso con su vigencia."))

    # ------------------------------------------------------------------ G-006 Sismo: noticia antigua recirculada
    vieja, m_vieja = _noticia("sismo-viejo", "TVN", "TVN", "Sismo de magnitud 5,6 sacude la zona fronteriza con Costa Rica",
                              "El Servicio Geológico de EE. UU. reportó el sismo frente a las costas de Burica.", "2025-12-17T23:30:00Z",
                              recirculada_en="2026-10-05T18:00:00Z")
    sismo, v_sismo = _sismo("us6000rvkl", "Sismo registrado el mismo día de la publicación original.")
    registrar(vieja, sismo)
    grupos.append(Grupo(
        "G-006", "Sismo de magnitud 5,6 frente a Burica (noticia recirculada)", "eventos_naturales", (m_vieja,),
        Puntaje.de(Componentes(R=0.5, I=0.5, U=0.0, N=0.0, E=1.0), _just(
            R="Evento natural en la región.", I="Sin daños reportados.", U="El evento ocurrió en diciembre de 2025.",
            N="Recirculación sin cambios: no es un evento nuevo.", E="Confirmado por el catálogo USGS.")),
        "parcial", "nuevo", (v_sismo,), None, None, True,
    ))

    # ------------------------------------------------------------------ G-007 Sin tema: no se fuerza una clase
    otro, m_otro = _noticia("concurso-tvn", "TVN", "TVN", "TVN estrena nueva temporada de su programa de concursos", None,
                            "2026-10-04T15:00:00Z")
    registrar(otro)
    grupos.append(Grupo(
        "G-007", "Estreno de temporada de un programa de concursos", "sin_tema", (m_otro,),
        Puntaje.de(Componentes(R=0.25, I=0.25, U=0.5, N=1.0, E=0.0), _just(
            R="Sin relación con los temas del reto.", I="Sin interés público demostrado.", U="Publicado hace 3 días.",
            N="Evento distinto.", E="Una procedencia sin datos que lo respalden.")),
        "insuficiente", "nuevo", (), "Fuera de los seis temas del reto: no se forzó un vínculo ni una clase.", None, True,
    ))

    consultas = (
        Respuesta("Q-1", "¿Cuántos tránsitos diarios limitará el Canal?", "respondida",
                  respuesta="La Autoridad del Canal informó que limitará a 32 los tránsitos diarios desde el 12 de octubre.",
                  citas=(cita_acp,)),
        Respuesta("Q-2", "¿Cuánto representaron las exportaciones de bienes y servicios en 2024?", "respondida",
                  respuesta="Representaron 44,36 % del PIB en 2024. Es un dato anual del Banco Mundial, no una medición actual.",
                  citas=(Cita(exp.id_evidencia, "valor", "44,36"),)),
        Respuesta("Q-3", "¿Cuál es la inflación de septiembre?", "contradiccion", versiones=(
            VersionContradictoria("1,1 %", "analistas citados por TVN", tvn_ipc.id_evidencia),
            VersionContradictoria("2,3 %", "informe privado citado por Metro Libre", ml_ipc.id_evidencia))),
        Respuesta("Q-4", "¿Cuál será el PIB de Panamá en 2027?", "abstencion",
                  motivo_abstencion="Ninguna fuente del corpus contiene una cifra de 2027.",
                  faltante="Una proyección oficial del PIB de 2027 con su fuente y fecha."),
    )
    revisiones = (
        RegistroRevision("CASO-001", "nuevo", None, "2026-10-07T12:00:00Z", None),
        RegistroRevision("CASO-001", "en_revision", DEMO_REVIEWER, "2026-10-07T13:00:00Z", "Pendiente confirmar la cifra con el comunicado."),
        RegistroRevision("CASO-002", "en_revision", DEMO_REVIEWER, "2026-10-07T13:10:00Z", "Esperando el dato oficial del INEC."),
        RegistroRevision("CASO-003", "requiere_evidencia", DEMO_REVIEWER, "2026-10-07T13:20:00Z", "Solo hay un titular."),
        RegistroRevision("CASO-005", "aprobado_como_borrador", DEMO_REVIEWER, "2026-10-07T13:30:00Z", "Aviso verificado con dos medios."),
    )
    return Paquete(tuple(ordenar_bandeja(grupos)), evidencias, tuple(fichas), consultas, revisiones)


def generar(directorio=DEMO) -> Paquete:
    """Writes the synthetic set and reads it back: what the interface loads must equal what was built."""
    paquete = construir()
    escribir(paquete, directorio, directorio)
    leido = cargar(directorio, directorio)
    if leido != paquete:
        raise AssertionError("los archivos de demostración no se leen igual que se escribieron")
    return leido
