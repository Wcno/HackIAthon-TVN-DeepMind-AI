---
title: Decisiones del equipo y desviaciones del reto
section: 0
source: decisión del equipo (no proviene del PDF)
summary: Desviaciones intencionales y reconocidas respecto al documento del reto. Tienen prioridad sobre las secciones 01-12 cuando hay conflicto.
---

# Decisiones del equipo y desviaciones del reto

Este archivo NO viene del PDF.
Registra decisiones propias del equipo que se apartan del documento original.
Si una sección `01`-`12` contradice este archivo, **prevalece este archivo**.

## D-01 · T10 (sin internet durante la demo) queda descartada

- **Qué dice el reto:** la prueba T10 exige que la app funcione con snapshot y fallback documentado sin internet, y deje evidencia en Notion (ver [09-pruebas-y-metricas.md](09-pruebas-y-metricas.md)).
  También el pitch pide una demo reproducible sin depender de una fuente en vivo (ver [10-entregables-y-rubrica.md](10-entregables-y-rubrica.md)).
- **Decisión:** el equipo descarta T10 como criterio de aceptación.
- **Motivo:** el modo offline no aporta valor para construir una buena app.
- **Reconocimiento:** es una desviación intencional y consciente respecto a la documentación.
- **Fallback opcional:** si alcanza el tiempo, se desarrollará una demo "offline" con datos pre guardados o similar.
  No es un requisito ni bloquea ninguna entrega.

### Cómo aplicar esta decisión

- No diseñar ni priorizar trabajo para T10.
- No contar T10 como pendiente o fallida al revisar el avance contra T01-T10.
- Mantener la arquitectura con carga por lote desde snapshot (sección 8): eso sigue vigente y facilita el fallback opcional.
- Si se construye el fallback, registrarlo en Notion como extra.
