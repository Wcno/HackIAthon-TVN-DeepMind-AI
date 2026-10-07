---
title: Decisiones del equipo y desviaciones del reto
section: 0
source: decisión del equipo (no proviene del PDF)
summary: Desviaciones y aclaraciones respecto al documento del reto. Tienen prioridad sobre las secciones 01-12 cuando hay conflicto.
---

# Decisiones del equipo y desviaciones del reto

Este archivo NO viene del PDF.
Registra decisiones propias del equipo y aclaraciones de la organización que se apartan del documento original.
Si una sección `01`-`12` contradice este archivo, **prevalece este archivo**.

## D-01 · T10 (sin internet durante la demo) está en alcance, con todo precalculado

- **Qué dice el reto:** la prueba T10 exige que la app funcione con snapshot y fallback documentado sin internet, y deje evidencia en Notion (ver [09-pruebas-y-metricas.md](09-pruebas-y-metricas.md)).
  También el pitch pide una demo reproducible sin depender de una fuente en vivo (ver [10-entregables-y-rubrica.md](10-entregables-y-rubrica.md)).
- **Decisión:** T10 vuelve a ser criterio de aceptación.
  La versión offline usa todo precargado y precalculado: corpus, embeddings, grupos, puntajes, fichas, borradores y respuestas a consultas.
- **Historial:** una versión anterior de esta decisión descartaba T10; la revisión de requisitos (R-01) la reemplazó.

### Cómo aplicar esta decisión

- Sin red, la caja de consultas solo responde consultas precalculadas (demo y benchmark).
  Una consulta nueva muestra «sin conexión: solo consultas precalculadas».
- No se usan modelos locales (ver `docs/adr/0001-gemini-free-tier-for-embeddings-and-generation.md`).
- La matriz de pruebas en Notion cubre T01-T10 y deja evidencia de la ejecución sin red.

## D-02 · Ventana de fechas: un año hacia atrás, desde 2025-10-02

- **Qué dice el reto:** el §6 pide los 30 días previos a la extracción y el §7 excluye registros fuera de `[2024-01-01, 2025-10-01)` (ver [06-datos-publicos.md](06-datos-publicos.md) y [07-contrato-de-datos.md](07-contrato-de-datos.md)).
  Ambas indicaciones son incompatibles entre sí y con la fecha del evento.
- **Decisión:** se usan registros desde 2025-10-02, un año hacia atrás.
  La fijó la organización fuera del PDF (R-02).
- **Alcance:** noticias y sismos USGS.
  Los indicadores del Banco Mundial conservan 2010-2024, por ser series anuales históricas.

### Cómo aplicar esta decisión

- El reporte de calidad registra los registros excluidos por la ventana y el motivo.
- El `manifest.json` guarda la ventana aplicada.

## D-03 · Fuentes abiertas

- **Qué dice el reto:** el §6 propone TVN RSS, GDELT, Banco Mundial, USGS y SBP.
- **Aclaración de la organización:** son ejemplos; el equipo puede usar las fuentes públicas que quiera.
- **Cómo aplicar:** se pueden añadir fuentes, registrando derechos y condiciones de reutilización de cada una.
