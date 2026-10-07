---
title: Contrato de datos y reproducibilidad
section: 7
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 7)
summary: Campos mínimos por archivo (noticias.csv, indicadores.csv, eventos.geojson, fichas.jsonl, manifest.json), reglas de integridad, normas de extracción y benchmark de 60 consultas.
---

# 7. Contrato de datos y reproducibilidad

## Archivos y campos mínimos

| Archivo | Campos mínimos |
| --- | --- |
| `noticias.csv` | `id_noticia`, `titulo`, `url`, `medio`, `idioma`, `fecha_publicacion`, `fecha_deteccion`, `fecha_extraccion`, `tema`, `origen`, `alcance_texto` |
| `indicadores.csv` | `pais_iso3`, `indicador_id`, `anio`, `valor` (nullable), `unidad`, `fuente_url`, `fecha_extraccion`, `licencia` |
| `eventos.geojson` | `id`, `magnitude`, `time`, `updated`, `longitude`, `latitude`, `depth`, `place`, `status` y URL del evento |
| `fichas.jsonl` | `id_caso`, `modalidad`, `ids_fuente`, `afirmaciones`, `citas`, `puntaje`, `componentes`, `estado_evidencia`, `borrador`, `estado_revision` |
| `manifest.json` | `versión`, `fecha_corte_UTC`, `consultas`, cantidad por archivo, licencia/condiciones, SHA-256 y transformaciones |

## Reglas de integridad

- UTF-8, IDs estables y fechas ISO 8601 en UTC.
  Mostrar hora de Panamá en la interfaz.
- Mantener la fecha de publicación distinta de `seendate` de GDELT, que indica detección.
- Conservar nulos y unidades originales.
  No rellenar ausencia de información con cero.
- Documentar revisiones, cambios de fuente y registros excluidos.
- Cada afirmación generada debe referenciar el ID de evidencia y el campo, pasaje o página que la respalda.
  Una URL sin relación con la afirmación no constituye una cita válida.

## Normas de extracción propuestas

- No asumir que el RSS conserva todo el histórico.
- Ejecutar una consulta por indicador y completar la cuadrícula de combinaciones faltantes.
- Excluir registros fuera del intervalo `[2024-01-01, 2025-10-01)`.

## Paquete común y conjunto reservado

- Guardar `raw/`, `processed/`, manifest y diccionario.
- Preparar `benchmark.jsonl` con **60 consultas**:
  - 30 de respuesta sustentada.
  - 10 de contradicción o ambigüedad.
  - 10 sin respuesta.
  - 10 adversariales.
- Usar 40 para desarrollo y reservar 20 al jurado, conservando los tipos.
- Las etiquetas se crean por revisión humana: no vienen de GDELT.
- Identificar los casos alterados como sintéticos.
- No mezclar respuestas reservadas con el corpus del agente.

## Ver también

- Orígenes de los datos: [06-datos-publicos.md](06-datos-publicos.md)
- Métricas sobre el benchmark: [09-pruebas-y-metricas.md](09-pruebas-y-metricas.md)
