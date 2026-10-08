# Diseño de solución

> Espeja la página «Diseño de solución» del §5. Documenta modelo, proveedor, versión,
> prompts, parámetros, costo medido y límites (§8).

## Arquitectura

```text
fuentes públicas (noticias, Banco Mundial, INEC, USGS)
   │  carga por lote, datos congelados en data/processed/ + manifest.json (SHA-256)
   ▼
embeddings locales (embeddinggemma-300m, ONNX q4)
   ▼
clasificación temática → agrupación → vínculo con indicador o evento → puntaje
   ▼
recuperación híbrida (BM25 + embeddings, fusión RRF)
   ▼
compuerta de abstención (similitud coseno ≥ 0,62)
   ▼
generación en dos pasos con esquema JSON estricto (gemini-3.5-flash-lite)
   ▼
verificador determinista de citas + verificación de implicación
   ▼
backend FastAPI + HTMX → revisión humana (SQLite) → exportación
```

Carga por lote; no hay monitoreo continuo. La demo no requiere internet.

## Stack y versiones

| Pieza | Elección | Versión |
| --- | --- | --- |
| Lenguaje | Python | 3.12 o superior (CI en 3.12, local en 3.14) |
| Dependencias | `uv` y `uv.lock` | fijadas |
| Servidor y vistas | FastAPI, Uvicorn, Jinja2, HTMX (ADR-0002) | `fastapi>=0.115`, `uvicorn>=0.30` |
| Validación de datos | Pydantic | `>=2.9` |
| Persistencia editorial | SQLite | biblioteca estándar |
| Cliente de modelos | `openai` apuntado a `GEMINI_BASE_URL` | `>=3.26` |
| Embeddings | `onnxruntime` y `tokenizers` | `onnxruntime>=1.30`, `tokenizers>=0.23` |
| Clasificación y agrupación | scikit-learn (regresión logística, agrupación aglomerativa) | `>=1.9` |
| Línea base de recuperación | BM25 propio | — |

## Modelos y parámetros

| Uso | Modelo | Parámetros | Costo medido |
| --- | --- | --- | --- |
| Respuestas, fichas, paquetes y verificación de implicación | `gemini-3.5-flash-lite` | salida JSON estricta, tope de tokens por llamada, espera de 20 s por defecto y 3 intentos (`WHOAMI_GENERATION_*`) | 70 llamadas y 46.280 tokens de red en la corrida final de G7 (ver `06`) |
| Temas, veredictos de agrupación y contradicciones | `gemma-4-26b-a4b-it` | JSON estricto, tope de tokens, timeout de 90 s, JSON inválido nunca se guarda | 3.484 llamadas en una noche de ejecución |
| Embeddings | `embeddinggemma-300m` (ONNX q4) | 768 dimensiones, prefijos de documento y consulta | 587 MB de memoria pico y 30 ms por consulta en 2 CPU |

Costo monetario: todo el uso fue en el tier gratuito. Google no publica límites exactos, así
que no se estima un costo en dólares. Los límites medidos figuran en `docs/adr/0001`.

## Reglas

**Puntaje de atención (`P = 30R + 25I + 20U + 15N + 10E`).** Cada componente va de 0 a 1.
U, N y E se calculan por regla. R e I combinan reglas con el modelo. Rangos: bajo
`[0, 40)`, medio `[40, 70)`, alto `[70, 100]`. Versión de reglas: 1.0.0.

**Estado de evidencia.** `insuficiente`, `parcial` o `suficiente_para_borrador`. Lo calcula
una regla y es independiente del puntaje. Prioridad alta con evidencia insuficiente no
habilita publicación.

**Procedencia independiente.** Una misma URL cuenta una vez. Una agencia nombrada (EFE, AP,
Reuters, AFP y similares) cuenta una vez aunque aparezca en varios dominios. Titulares casi
idénticos cuentan como replicación.

**Abstención.** El modelo puede proponer abstenerse, pero la decisión la toma el código:
si la similitud de recuperación queda bajo 0,62, no se llama al modelo para generar.

## Prompts y control del modelo

- La evidencia viaja codificada en JSON dentro de un mensaje `user`. La política de contenido
  no confiable va en el `system`. Las instrucciones propias van en un turno posterior.
- El agente no tiene herramientas con efecto: no publica, no escribe en Notion y no ve secretos.
- Los límites de palabras del brief (250) y del copy (80) se validan en código.
- Cada llamada tiene un tope de tokens, de modo que una salida degenerada falle rápido.

## Límites del sistema

- Solo metadatos de los medios. Si no hay cuerpo del artículo, la salida lo dice:
  «basado únicamente en titular/metadatos».
- El prototipo no etiqueta noticias como verdaderas o falsas.
- Las acusaciones se atribuyen como declaraciones, nunca como hechos.
- El tono, el volumen o la repetición de una noticia no equivalen a verdad comprobada.
