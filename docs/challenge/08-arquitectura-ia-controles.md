---
title: Arquitectura, IA y controles
section: 8
source: docs/raw/hackIAthon - reto TVN Media.pdf (p. 8)
summary: Arquitectura mínima, requisitos de uso sustantivo de IA, y controles obligatorios de seguridad, anti-alucinación, anti-inyección, privacidad y derechos.
---

# 8. Arquitectura, IA y controles

## Arquitectura mínima sugerida

```text
Fuentes públicas / snapshot
  → validación y normalización
  → almacenamiento
  → búsqueda y agrupación
  → motor de priorización
  → generación con evidencias
  → interfaz
  → revisión humana
  → registro en Notion
```

Para el MVP basta una carga por lote.
No se exige monitoreo continuo ni acceso a internet durante el pitch.

## Uso sustantivo de inteligencia artificial

- Implementar al menos una capacidad de ML/NLP: clasificación semántica, similitud para agrupar eventos, extracción de entidades o recuperación semántica.
  Un conjunto de IF/ELSE no basta como uso de IA.
- Generar respuestas y borradores sobre evidencia recuperada.
  Si se usa un LLM, separar instrucciones del contenido de fuentes y exigir estructura de salida con citas y vacíos de información.
- Comparar al menos una tarea con un baseline simple: búsqueda por palabras clave, reglas temáticas o ranking por fecha.
  Explicar qué mejora aporta la IA y cuándo no ayuda.
- Documentar modelo/proveedor, versión, prompts, parámetros, costo medido y limitaciones.
- El stack es libre; no se obliga a contratar APIs ni bases de datos comerciales.

## Seguridad y ética obligatorias

- **Control humano:** los estados son `nuevo`, `en revisión`, `requiere evidencia`, `aprobado como borrador` y `descartado`.
  Aprobar un borrador no significa publicar.
- **Anti-alucinación:** no inventar hechos, declaraciones, entrevistados, cifras, causalidades ni fuentes.
  Si falta evidencia, abstenerse y explicar qué información se necesita.
- **Anti-inyección:** el texto de una fuente es dato, no instrucción.
  Un artículo que pide revelar secretos o cambiar reglas nunca debe modificar el comportamiento del agente.
- **Privacidad y reputación:** evitar almacenar datos personales innecesarios.
  No crear perfiles sensibles ni listas de supuestos delincuentes o clientes riesgosos.
  Las acusaciones se atribuyen como declaraciones, no como hechos probados.
- **Derechos y acceso:** registrar condiciones por fuente; no redistribuir artículos, imágenes o videos sin permiso.
  Notion debe compartirse solo con participantes y jurado autorizados; no es obligatorio publicar el espacio en la web.
- **Credenciales:** fuera del código y de Notion público.
  No registrar tokens ni secretos en capturas, prompts o logs.
  Mantener dependencias y costos bajo control.

> Una alerta es una invitación a investigar.
> Ni tono negativo, ni volumen de noticias, ni repetición equivalen a fraude, pérdida financiera o verdad comprobada.

## Ver también

- Pruebas de seguridad (T06, T07): [09-pruebas-y-metricas.md](09-pruebas-y-metricas.md)
