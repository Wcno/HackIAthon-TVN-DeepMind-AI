---
title: En qué consiste el prototipo
section: 3
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 3)
summary: Flujo de 7 etapas (Cargar a Revisar) y formato de salida TVN (paquete editorial) y banca (boletín).
---

# 3. En qué consiste el prototipo

El equipo elige una modalidad, explica quién usa el producto y ejecuta el flujo de extremo a extremo.
Una interfaz web, dashboard o notebook interactivo es válido si permite demostrar todo el recorrido.

## Flujo de 7 etapas

| Etapa | Comportamiento mínimo esperado |
| --- | --- |
| 1 · Cargar | Leer el paquete público congelado. Validar IDs, URLs, fechas, campos obligatorios y filas nulas. Emitir un reporte de calidad. |
| 2 · Organizar | Clasificar temas: economía, logística/Canal, turismo, servicios públicos, eventos naturales y regulación. Agrupar noticias sobre el mismo evento. |
| 3 · Contextualizar | Relacionar noticias con indicadores o eventos oficiales pertinentes. Mostrar período, unidad y limitaciones. Si no existe relación sustentada, no forzarla. |
| 4 · Priorizar | Calcular un puntaje de atención, mostrar componentes y generar una lista ordenada. Distinguir relevancia de suficiencia de evidencia. |
| 5 · Explicar | Abrir una ficha: qué se reporta, quién lo reporta, qué está respaldado, qué falta comprobar y qué acción se recomienda al usuario. |
| 6 · Producir | Redactar un borrador propio de la modalidad, con citas por afirmación. Diferenciar hechos, declaraciones, inferencias e hipótesis. |
| 7 · Revisar | Registrar aceptación, corrección o descarte por una persona responsable. Crear o actualizar manualmente la ficha en Notion; automatizar este paso es opcional. |

## Salida TVN: paquete editorial

- Brief de hasta 250 palabras.
- Título propuesto.
- Enfoque de interés público.
- 3 preguntas de investigación.
- Fuentes y verificaciones pendientes.
- Borrador de guion de 45-60 segundos.
- Copy digital de hasta 80 palabras.
- No inventar entrevistas, citas, imágenes disponibles ni afirmaciones no respaldadas.

## Salida bancaria: boletín de entorno

- Resumen de hasta 250 palabras.
- Sectores potencialmente relacionados, horizonte temporal y evidencia.
- 3 preguntas para el analista.
- Separar observación de hipótesis de impacto.
- No recomendar compra/venta ni inferir pérdidas, impagos o exposición de una cartera inexistente.

## Restricción común

Si solo se dispone del titular y metadatos, la salida debe decir **"basado únicamente en titular/metadatos"**.
No simular la lectura del artículo completo ni atribuirle detalles adicionales.

## Ver también

- Puntaje y casos de uso: [04-casos-de-uso-y-priorizacion.md](04-casos-de-uso-y-priorizacion.md)
- Contrato de datos (`fichas.jsonl`): [07-contrato-de-datos.md](07-contrato-de-datos.md)
