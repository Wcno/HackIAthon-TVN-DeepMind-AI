---
title: Índice del reto hackIAthon TVN Media
source: docs/raw/hackIAthon - reto TVN Media.pdf
language: es
---

# hackIAthon · Reto TVN Media: "De la señal a la decisión"

Copiloto de inteligencia informativa y análisis de entorno con IA.
Este directorio es la versión consultable por IA del PDF original (`docs/raw/hackIAthon - reto TVN Media.pdf`).
Cada archivo cubre una sección del PDF, es autocontenido y lleva frontmatter con `summary`.

**Cómo usarlo:** lee este índice, elige el archivo según la pregunta y abre solo ese.
Los IDs (`CU-01`, `T01`, `R/I/U/N/E`) y los nombres de archivo de datos son estables y se pueden buscar con grep.

> **Desviaciones del equipo:** lee primero [00-decisiones-del-equipo.md](00-decisiones-del-equipo.md).
> Prevalece sobre el PDF.
> Hoy: T10 está en alcance con todo precalculado (D-01); ventana de fechas desde 2025-10-02 (D-02); fuentes abiertas (D-03).

## Resumen en 5 líneas

- Prototipo que convierte noticias públicas + indicadores oficiales en temas priorizados, fichas de evidencia y borradores para revisión humana.
- Modalidad recomendada: editorial (TVN); banca es alternativa o extensión.
- Notion es obligatorio (ejecución, documentación y pitch de 10 min).
- Datos: noticias (TVN RSS + GDELT), Banco Mundial, USGS; SBP opcional.
- Nada se publica automáticamente; toda afirmación lleva cita; ante falta de evidencia, abstenerse.

## Mapa de secciones

| Archivo | Sección | Responde a |
| --- | --- | --- |
| [00-decisiones-del-equipo.md](00-decisiones-del-equipo.md) | n/a | Desviaciones y aclaraciones respecto al PDF (T10 offline, ventana de fechas, fuentes abiertas). |
| [01-resumen-ejecutivo.md](01-resumen-ejecutivo.md) | 1 | ¿Qué es el reto y cuáles son las condiciones esenciales? |
| [02-problema-y-alcance.md](02-problema-y-alcance.md) | 2 | ¿Quién usa el producto? ¿Qué entra y qué NO entra en el MVP? |
| [03-prototipo-flujo.md](03-prototipo-flujo.md) | 3 | ¿Qué etapas tiene el flujo? ¿Cómo debe verse el brief/guion/boletín? |
| [04-casos-de-uso-y-priorizacion.md](04-casos-de-uso-y-priorizacion.md) | 4 | CU-01..CU-05, fórmula del puntaje 0-100, estado de evidencia. |
| [05-notion.md](05-notion.md) | 5 | Estructura de Notion y requisitos mínimos de admisión. |
| [06-datos-publicos.md](06-datos-publicos.md) | 6 | Qué datos, de dónde, cuántos, qué filtros y qué derechos. |
| [07-contrato-de-datos.md](07-contrato-de-datos.md) | 7 | Esquemas de archivos, reglas de integridad, benchmark de 60 consultas. |
| [08-arquitectura-ia-controles.md](08-arquitectura-ia-controles.md) | 8 | Arquitectura, requisitos de IA, seguridad, anti-alucinación y anti-inyección. |
| [09-pruebas-y-metricas.md](09-pruebas-y-metricas.md) | 9 | Pruebas T01-T10 y metas de métricas. |
| [10-entregables-y-rubrica.md](10-entregables-y-rubrica.md) | 10 | Qué se entrega y cómo se puntúa (100 pts). |
| [11-ejecucion-y-pitch.md](11-ejecucion-y-pitch.md) | 11 | Cronograma por tramos, pitch de 10 min, preguntas del jurado. |
| [12-fuentes-y-notas.md](12-fuentes-y-notas.md) | 12 | URLs de fuentes, criterio de éxito, plan por días. |

## Atajos por tema

- **Fórmula del puntaje:** `P = 30R + 25I + 20U + 15N + 10E` → [04](04-casos-de-uso-y-priorizacion.md)
- **Rúbrica del jurado:** → [10](10-entregables-y-rubrica.md)
- **Qué NO hacer (límites):** → [02](02-problema-y-alcance.md) y [08](08-arquitectura-ia-controles.md)
- **Campos de `noticias.csv`, `fichas.jsonl`, etc.:** → [07](07-contrato-de-datos.md)
- **Indicadores del Banco Mundial (IDs):** → [06](06-datos-publicos.md)
- **Estados de revisión humana:** → [08](08-arquitectura-ia-controles.md)
- **Entregables del repo (README, .env.example, tests):** → [10](10-entregables-y-rubrica.md)

## Nota sobre la conversión

- Contenido fiel al PDF; las tablas se conservan como tablas Markdown.
- Los guiones largos del original se reemplazaron por guiones simples "-".
- Las URLs de la sección 12 se recuperaron de los hipervínculos del PDF.
