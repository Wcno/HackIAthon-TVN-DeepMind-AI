# Casos y evidencias

> Espeja la página «Casos y evidencias» del §5. Evidencia mínima: al menos 5 fichas
> trazables, incluido un caso sin evidencia suficiente. Las fichas salen de
> `outputs/fichas.jsonl`; esta página es su vista legible.

## Casos de uso

| ID | Caso | Qué se ve en la demo | Estado |
| --- | --- | --- | --- |
| CU-01 | Temas para la agenda de Panamá, con razones | Bandeja ordenada por puntaje, con componentes R, I, U, N y E | Implementado |
| CU-02 | Tema económico con una serie oficial | Cifra del Banco Mundial con país, año y unidad, sin presentarla como cifra de hoy | Implementado |
| CU-03 | Titulares repetidos | Una agencia replicada cuenta como una procedencia | Implementado; sin marcador de agencia en el corpus actual |
| CU-04 | Pregunta sin respuesta o con contradicción | Abstención explícita o ambas versiones con su verificación pendiente | Implementado |

Glosario: **CU-xx** es un caso de uso del reto; **CASO-…** es el ID de una ficha; **G-…** es un
grupo de noticias (`grupos.jsonl`), que puede o no tener ficha.

## Fichas

Fichas generadas en `outputs/fichas.jsonl` (5 casos):

| `id_caso` | Tema | Título (resumen) | Estado de evidencia | Puntaje | Revisión |
| --- | --- | --- | --- | --- | --- |
| `CASO-bc61489f19` | economía | Mides solicita $47 millones para el último pago de transferencias de 2026 | parcial | alto | nuevo |
| `CASO-7eec9567e8` | regulación | Talleres sobre el Reglamento de Alimentos Sensitivos en Bocas del Toro y Chiriquí | suficiente para borrador | alto | nuevo |
| `CASO-f15debf340` | economía | Comisión de Presupuesto tramita traslados y créditos por casi $100 millones | parcial | alto | nuevo |
| `CASO-5ae7185008` | economía | Enfrentamiento en la Comisión de Presupuesto entre Yamireliz Chong y Benicio Robinson | parcial | alto | nuevo |
| `CASO-fc933530e0` | logística y Canal | Navieras de Vietnam ratifican su confianza en el registro de barcos y el Canal | suficiente para borrador | alto | nuevo |

Todas las fichas están en `nuevo`. Ninguna se ha aprobado, y **ninguna tiene persona revisora
asignada**; aprobar no equivale a publicar.

## Caso sin evidencia suficiente

**Requisito no cumplido de forma literal:** el §5 pide una ficha con evidencia insuficiente. Las
fichas anteriores no incluyen ningún caso `insuficiente`, porque el generador omite los grupos
sin evidencia suficiente. Mientras el equipo decide si genera una ficha de abstención, el caso
se presenta como grupo, `G-61c55dfdbb` (`data/processed/grupos.jsonl`):

- **Titular:** «PASE-U: compras con la billetera de Caja de Ahorros superan los $45 millones desde junio».
- **Puntaje:** 83,24 (alto). Componentes: R 1,0 · I 0,8 · U 1,0 · N 0,79 · E 0,13.
- **Estado de evidencia:** `insuficiente`. Una sola procedencia, sin fuente primaria y solo titular.
- **Contexto oficial:** ninguno. El motivo es que ningún indicador ni evento mide este tema, así que no se forzó un vínculo.
- **Qué se muestra:** puntaje alto y estado insuficiente a la vez. La prioridad no habilita publicación (T08).

## Consultas precalculadas (CU-04)

`outputs/consultas.jsonl` tiene 35 consultas: 13 respondidas, 5 con contradicción y 17 con
abstención. Ejemplo de respondida, con cita literal: «¿A cuántos tránsitos diarios aumentará el
Canal de Panamá y desde cuándo?». La respuesta cita la descripción de la noticia N-05f712d5caeb.

## Plantilla de ficha

- `id_caso` y modalidad (`editorial_tvn`).
- `ids_fuente`: IDs de evidencia (`N-…`, `WB-…`, `USGS-…`, `INEC-…`).
- `afirmaciones`: texto, tipo (hecho, declaración, inferencia o hipótesis), IDs de evidencia y pasaje literal.
- `citas`: resultado del verificador. Los fallos se muestran, no se ocultan.
- `puntaje` y `componentes`, con la versión de reglas.
- `estado_evidencia`: calculado por regla, corregible por la persona revisora.
- `borrador`: brief, título propuesto, tres preguntas de investigación, guion y copy.
- `estado_revision`: `nuevo`, `en_revision`, `requiere_evidencia`, `aprobado_como_borrador` o `descartado`.
- Persona revisora y fecha de la decisión.

## Preguntas del jurado (§11)

1. **«¿De dónde sale esta cifra y de qué año es?»** Ficha con `evidencia_id`, período y unidad.
2. **«Si cinco medios replican la misma agencia, ¿cuántas fuentes independientes cuentas?»**
   Una. Se muestra el conteo que alimenta el componente E.
3. **«¿Qué pasa si no hay evidencia o una fuente intenta cambiar las instrucciones?»**
   Abstención (CU-04) y titular adversarial sintético (T07).
4. **«Muéstrame una decisión, una prueba fallida y su corrección».** Ver `02-plan-y-decisiones.md`,
   sección «Hallazgos».
