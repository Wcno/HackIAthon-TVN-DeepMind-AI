---
title: Fuentes y notas para la implementación
section: 12
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 12)
summary: URLs y notas de las 9 fuentes públicas ([1]-[9]), criterio de éxito y plan sugerido por días (3 días).
---

# 12. Fuentes y notas para la implementación

Fuentes públicas identificadas para diseñar el paquete de pruebas.
Fecha de consulta: 05/10/2026.
Se verificaron páginas y documentación; no se descargó ni auditó el dataset completo.

| # | Fuente | URL | Notas |
| --- | --- | --- | --- |
| 1 | TVN Panamá · sitio oficial | https://www.tvn-2.com/ | |
| 2 | TVN · feed RSS público | https://www.tvn-2.com/rss/ | Base para titulares y enlaces del patrocinador. El RSS contiene noticias, fechas y descripciones; eso no implica licencia abierta sobre artículos, videos o imágenes. |
| 3 | GDELT · documentación DOC 2.0 API | https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts | Documenta ArtList, filtros por dominio/idioma, ventanas temporales y límite de 250 resultados. Verificar funcionamiento al congelar el paquete. No confundir con servicios comerciales llamados GDELT Cloud. |
| 4 | Banco Mundial · Indicators API v2 | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation | |
| 5 | Banco Mundial · indicadores de Panamá | https://data.worldbank.org/country/panama | |
| 6 | Banco Mundial · términos para datasets | https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets | Aplicar atribución y revisar excepciones de terceros por indicador. Los datos pueden revisarse y su período de referencia no coincide necesariamente con el año de extracción. |
| 7 | USGS · catálogo sísmico y parámetros del servicio | https://earthquake.usgs.gov/fdsnws/event/1 | Usar IDs y URL de evento para trazabilidad. Confirmar condiciones aplicables a datos o elementos de terceros. |
| 8 | SBP · estadísticas financieras | https://www.superbancos.gob.pa/estadisticas-financieras | Extensión local para la modalidad bancaria. |
| 9 | SBP · estudios e informes publicados | https://www.superbancos.gob.pa/estadisticas-financieras/estudios | Seleccionar los informes y columnas antes del evento, conservando las advertencias de uso informativo y las condiciones correspondientes. |

> Nota de conversión: el PDF muestra los títulos como hipervínculos.
> Las URLs se extrajeron de las anotaciones del PDF y se asignaron a cada fuente por orden de aparición.

## Criterio de éxito

El proyecto será convincente si:

- Una persona de editorial puede pasar de un conjunto disperso de fuentes a un tema investigable, con evidencia y un borrador responsable.
- O un analista bancario puede construir un boletín de entorno sustentado.

La calidad de la decisión asistida, la trazabilidad en Notion y la capacidad de reconocer lo que no se sabe importan más que el volumen de texto generado.

## Plan sugerido por días

- **Día 1 · Datos y diseño:** preparar las fuentes, definir arquitectura, crear el espacio Notion e implementar la carga.
  Núcleo de IA: búsqueda, agrupación de noticias, priorización y respuestas con evidencias.
- **Día 2 · Producto funcional:** interfaz, fichas, generación de briefs/guiones y revisión humana.
- **Día 3 · Pruebas y cierre:** validar citas, contradicciones, consultas sin respuesta y resistencia a instrucciones maliciosas.
  Corregir fallos, completar métricas y Notion, preparar y ensayar la presentación.

## Ver también

- Cómo se usan las fuentes: [06-datos-publicos.md](06-datos-publicos.md)
- Ruta del evento: [11-ejecucion-y-pitch.md](11-ejecucion-y-pitch.md)
