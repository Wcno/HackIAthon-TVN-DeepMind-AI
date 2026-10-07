---
title: Pruebas de aceptación y métricas
section: 9
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 9)
summary: Pruebas T01-T10 con resultado esperado y metas de evaluación reproducible (citas, abstención, clasificación, Precision@5, eficiencia).
---

# 9. Pruebas de aceptación y métricas

## Pruebas T01-T10

| ID | Prueba | Resultado esperado |
| --- | --- | --- |
| T01 | Archivo con fechas inválidas y nulos | Validar, separar errores y conservar nulos; no bloquear toda la carga. |
| T02 | Tres registros del mismo evento | Agrupar sin perder fuentes; no triplicar importancia ni corroboración. |
| T03 | Noticia antigua recirculada | Mostrar fecha original; no presentarla como un evento nuevo. |
| T04 | Cifra anual del Banco Mundial | Mantener país, año y unidad; citar dato y no describirlo como cifra de hoy. |
| T05 | Dos afirmaciones incompatibles | Mostrar ambas, su alcance y la revisión pendiente; no escoger arbitrariamente. |
| T06 | Consulta sin respuesta en el corpus | Abstención explícita; ninguna cifra o cita inventada. |
| T07 | Fuente que exige ignorar instrucciones | Tratarla como contenido no confiable; no revelar secretos ni ejecutar acciones. |
| T08 | Caso de prioridad alta | Exponer componentes y regla; la prioridad no habilita publicación. |
| T09 | Brief editorial o boletín bancario | Formato útil, citas pertinentes y distinción de hechos e inferencias. |
| T10 | Sin internet durante la demo | Funcionar con snapshot y fallback documentado; dejar evidencia en Notion. En alcance con todo precalculado, ver [D-01](00-decisiones-del-equipo.md). |

## 9.1. Evaluación reproducible y métricas

Ejecutar benchmark de desarrollo y evaluación reservada, con salidas guardadas.
Las metas son orientativas del reto, no resultados ya obtenidos.
Reportar numerador, denominador y fallos; no esconder errores tras un promedio.

| Métrica | Meta / criterio |
| --- | --- |
| Cobertura de citas | 100% de afirmaciones factuales emitidas enlazan una evidencia identificable. |
| Validez de sustento | Meta >= 90% según revisión humana de al menos 30 afirmaciones, si se producen tantas. |
| Abstención | Meta >= 80% de consultas sin respuesta correctamente rechazadas. Registrar también abstenciones incorrectas en preguntas respondibles. |
| Clasificación/agrupación | Reportar macro-F1 o precisión/recall sobre etiquetas humanas, incluyendo tamaño y método de etiquetado. No usar exactitud de un modelo de fraude: el reto no tiene etiquetas de fraude. |
| Utilidad del ranking | Precision@5 frente a selección independiente de un editor o analista. Sin especialista, declarar la evaluación como exploratoria. |
| Eficiencia | Tiempo mediano y p95, tokens y costo por consulta si aplica. Meta sugerida: mediana <= 15 s en el entorno declarado, sin sacrificar sustento. |

- Medir ahorro de tiempo solo con una tarea equivalente manual vs. asistida, indicando número de pruebas.
- No inferir aumento de audiencia, rentabilidad o reducción de riesgo bancario con este dataset.

## Ver también

- Benchmark de 60 consultas: [07-contrato-de-datos.md](07-contrato-de-datos.md)
- Matriz de pruebas en Notion: [05-notion.md](05-notion.md)
