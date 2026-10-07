---
title: Casos de uso y priorización explicable
section: 4
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 4)
summary: Casos de uso CU-01 a CU-05, fórmula del puntaje de atención 0-100 y estado de evidencia.
---

# 4. Casos de uso y priorización explicable

## Casos de uso que debe demostrar el equipo

- **CU-01 · TVN:** "¿Qué cinco temas merecen revisión para la agenda de Panamá y por qué?".
  Mostrar ranking, evidencia disponible y vacíos de verificación.
- **CU-02 · TVN:** abrir un tema económico, incorporar una serie oficial y redactar un brief sin confundir un dato anual histórico con una medición de hoy.
- **CU-03 · Común:** agrupar titulares repetidos y distinguir repetición de corroboración independiente.
  Una agencia replicada cuenta como una sola procedencia.
- **CU-04 · Común:** preguntar por una cifra inexistente o por una contradicción.
  Abstenerse o mostrar las versiones y la verificación pendiente.
- **CU-05 · Banca:** "¿Qué señales públicas del entorno logístico debo revisar?".
  Entregar contexto sectorial, no un score de clientes ni una alerta regulatoria definitiva.

## Puntaje de atención sugerido: 0-100

Es una herramienta de ordenamiento, no una probabilidad de verdad ni de pérdida.
Cada componente se normaliza a 0-1 con criterios documentados.
Pesos iniciales propuestos:

| Componente | Peso | Qué mide |
| --- | --- | --- |
| R · Relevancia | 30 | Relación con Panamá y con los temas de la modalidad. |
| I · Impacto potencial | 25 | Interés público o alcance sectorial, justificado con datos; no con sensacionalismo. |
| U · Urgencia | 20 | Tiempo disponible para revisar una información o un evento. |
| N · Novedad | 15 | Diferencia frente a eventos ya agrupados; duplicación no incrementa el puntaje. |
| E · Evidencia disponible | 10 | Fuentes pertinentes, primarias y con procedencia identificable. |

**Fórmula:** `P = 30R + 25I + 20U + 15N + 10E`

- Rangos sin solapamiento: bajo `[0,40)`, medio `[40,70)`, alto `[70,100]`.
- Empates: mayor urgencia y luego ID.
- Mostrar la versión de reglas y permitir justificar cambios de pesos.

## Estado de evidencia (independiente del puntaje)

Valores: **"insuficiente"**, **"parcial"** o **"suficiente para el borrador"**.

- Una prioridad alta con evidencia insuficiente requiere investigación; no habilita publicación.
- El prototipo no debe etiquetar automáticamente una noticia como verdadera o falsa.
- La persona revisora conserva la decisión editorial o analítica final.

## Ver también

- Pruebas relacionadas (T02, T04, T05, T06, T08): [09-pruebas-y-metricas.md](09-pruebas-y-metricas.md)
