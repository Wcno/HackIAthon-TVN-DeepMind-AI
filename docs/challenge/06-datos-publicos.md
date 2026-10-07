---
title: Set de datos públicos de prueba
section: 6
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 6)
summary: Paquete "Panamá · Señales y Evidencias v1" - fuentes A (noticias), B (Banco Mundial), C (USGS), D (SBP opcional) con volúmenes, filtros y restricciones de uso.
---

# 6. Set de datos públicos de prueba

Paquete propuesto: **"Panamá · Señales y Evidencias v1"**.
Los volúmenes son metas de preparación, no datos ya descargados.
La organización debe congelar una versión común antes del evento y usarla para todos los equipos.

- Núcleo obligatorio: A + B.
- C añade eventos verificables.
- D es una extensión bancaria opcional.

## A · Noticias públicas: TVN RSS + GDELT DOC 2.0

- **Meta:** 200 registros únicos. **Mínimo operativo:** 100, con al menos 20 de TVN.
- Recopilar titulares, URLs, medio, idioma y marcas temporales de los 30 días previos a la extracción.
- Si faltan registros, ampliar hasta 90 días y registrar la cobertura efectiva.
- GDELT se consulta por "Panama", logística, turismo, economía y eventos naturales.
- La API devuelve como máximo 250 artículos por consulta: dividir por fechas y deduplicar por URL.
- **Archivos:** `noticias.csv` y `fuentes.json`.
- No exigir cuerpos completos ni videos.
- En TVN usar inicialmente los metadatos.
  Reutilizar extractos o contenido completo solo bajo condiciones aplicables o autorización explícita del patrocinador.
- El patrocinio no concede por sí solo derechos de republicación.
- La API de GDELT tampoco transfiere derechos de los medios enlazados.

## B · Banco Mundial: contexto económico comparable

- **Países (6):** PAN, CRI, COL, DOM, MEX y GTM.
- **Años:** 2010-2024.
- **Indicadores (6):**

| ID | Indicador |
| --- | --- |
| `NY.GDP.MKTP.KD.ZG` | Crecimiento del PIB |
| `FP.CPI.TOTL.ZG` | Inflación |
| `SL.UEM.TOTL.ZS` | Desempleo |
| `SP.POP.TOTL` | Población |
| `IT.NET.USER.ZS` | Uso de internet |
| `NE.EXP.GNFS.ZS` | Exportaciones/PIB |

- **Archivo:** `indicadores.csv`.
- Cuadrícula de 1.350 combinaciones país × indicador × año (6 × 6 × 15 · valores faltantes se conservan explícitamente).
- No prometer 1.350 observaciones válidas.
- **Uso:** respaldar cifras, comparar períodos y evitar inventar datos actuales.
- **Licencia:** CC BY 4.0, salvo excepciones indicadas en metadatos.

## C · USGS: eventos sísmicos oficiales

- **Archivo:** `eventos.geojson`.
- Extraer sismos del 01/01/2024 al 31/12/2024.
- Caja regional: latitud 5 a 12, longitud -86 a -76.
- Magnitud mínima: 3.
- Volumen: todos los eventos devueltos; no fijar un número ficticio.
- La caja no equivale al territorio de Panamá.
- Mantener ubicación y usar la fuente solo para hechos sísmicos, nunca como evidencia de inundación o de pérdidas económicas.

## D · SBP: extensión bancaria opcional

- Seleccionar 12 informes mensuales disponibles del año 2024, o un período de 12 meses documentado, de la Superintendencia de Bancos de Panamá.
- Extraer series agregadas con período, unidad y página de origen.
- Son datos informativos, revisables; validar condiciones de reutilización.
- No incluir información de clientes.
- No confundir análisis del equipo con una opinión oficial de la SBP.

## Ver también

- Campos y formatos de cada archivo: [07-contrato-de-datos.md](07-contrato-de-datos.md)
- URLs de las fuentes: [12-fuentes-y-notas.md](12-fuentes-y-notas.md)
