# G7: evaluación reproducible

El issue [G7 / #25](https://github.com/Wcno/hackiaton-whoamisfc/issues/25) se ejecuta con:

```powershell
$env:WHOAMI_EMBEDDING_THREADS = '2'
uv run --locked whoami evaluar --mode live --human-reviews C:/ruta/revisiones
```

Requiere el modelo ONNX de EmbeddingGemma descargado y `GEMINI_API_KEY` en el
entorno o en `.env`. Usa la configuración y los límites de la capa compartida
`whoami.llm`. La ejecución guarda respuestas, fichas, predicciones, rankings,
métricas, el resultado de pytest y la comprobación HTTP de T10 en
`outputs/evaluation/g7/`. Los errores de proveedor quedan separados de las
abstenciones correctas. No se registran credenciales.

Para reproducir la evaluación sobre respuestas existentes, sin llamadas a
Gemini:

```powershell
uv run --locked whoami evaluar --mode recorded
```

Este modo vuelve a medir la recuperación y valida las respuestas de
`outputs/consultas.jsonl` que coinciden exactamente con la pregunta. Las
consultas sin respuesta archivada se reportan como faltantes y permanecen en
el denominador. Los tiempos y tokens originales de generación se reportan
como no disponibles; no se sustituyen por el tiempo de lectura del archivo.

El código de salida es `0` cuando todos los requisitos medibles y de revisión
están completos y `2` si hay requisitos pendientes. `--skip-tests` permite
iterar, pero su ejecución no satisface la aceptación de G7.

## Corpus y separación del benchmark

Se evalúa el snapshot de G3/G4 en `data/processed/evidencias.jsonl`, con
2.941 noticias y sus vectores alineados mediante los IDs del manifest. El CSV
de noticias de G1 puede corresponder a una extracción más reciente; no se
mezclan sus posiciones con las de estos vectores. Se comprueban el SHA-256,
las dimensiones, la finitud y la cobertura exacta del corpus de noticias.

Las fuentes sintéticas de prueba están separadas, tienen IDs `N-syn*` y URLs
`.invalid`; solo entran al corpus de evaluación. Las preguntas, sus respuestas
esperadas y las etiquetas no son documentos recuperables ni se envían en los
prompts. Los índices de evaluación se guardan fuera del repositorio y su clave
incluye el contenido de las fuentes y la revisión del modelo.

El benchmark tiene 60 consultas: 30 sustentadas, 10 de contradicción o
ambigüedad, 10 sin respuesta y 10 adversariales. El conjunto de desarrollo
contiene 40 (20/7/7/6). El conjunto reservado contiene 20 (10/3/3/4), con
preguntas distintas, y se guarda fuera del checkout, en
`~/.cache/whoami/evaluation/g7-reserved/benchmark.jsonl`. El manifest público
solo contiene cantidades, distribución y SHA-256 del paquete reservado.

La ejecución habitual no abre el paquete reservado. El jurado puede ejecutar:

```powershell
uv run --locked whoami evaluar --mode live --reserved C:/ruta/benchmark.jsonl --output outputs/evaluation/jurado
```

El paquete se creó mediante un script de preparación que se conserva junto
al archivo reservado, fuera del checkout. Tanto ese script como las consultas
y sus claves esperadas quedan fuera de Git. El manifest permite verificar el
paquete original sin regenerarlo después de ajustar el sistema. El
contenido reservado no se usa para calibrar umbrales.
Las propuestas de etiquetas del benchmark requieren revisión humana.

## Métodos y métricas

| Tarea | Comparación y medición |
| --- | --- |
| Recuperación | BM25, embeddings y fusión RRF, sobre las mismas fuentes y consultas; recall@8 macro y micro, con fallos por ID. |
| Clasificación | Palabras clave frente a regresión logística sobre embeddings; 5 folds estratificados, semilla 7, sin entrenar con el fold evaluado. Macro-F1 de las 7 clases, resultados por clase y aciertos/total. |
| Agrupación | Titulares casi idénticos y ventana temporal frente al agrupador de producción con embeddings, average linkage y 72 horas, sin overrides nuevos del LLM. Precisión, recall y F1 sobre los 345 pares. Etiqueta 2 significa mismo evento; 0 y 1 se consideran negativos y no se descartan. |
| Respuestas | Estado esperado, claves y controles adversariales; aciertos/total y fallos, incluyendo respuestas faltantes. |
| Abstención | Correctas sobre consultas sin respuesta e incorrectas sobre las respondibles, con denominadores distintos. |
| Citas | Cobertura de referencias literales en respuestas y afirmaciones; distinta de la validez semántica de sustento. |
| Sustento humano | Afirmaciones únicas respaldadas / revisadas, tamaño de muestra y errores de revisión; mínimo 30, meta del 90%. |
| Eficiencia | Mediana y p95 por nearest rank. La recuperación incluye el embedding de la pregunta, con calentamiento y construcción del índice fuera del tiempo por consulta. Generación incluye recuperación, gate y llamadas del modelo. |
| Tokens | Uso comunicado por el proveedor, llamadas de red y caché por separado. Tokens de solicitudes fallidas y costo no conocido se reportan como no disponibles. |

La evaluación de clasificación sigue siendo exploratoria: la selección del
modelo en G3 utilizó las mismas etiquetas propuestas. La validación cruzada
evita entrenar con el fold de prueba, pero no convierte este conjunto en una
evaluación independiente de selección de modelo. Precision@5 editorial queda
fuera del alcance de G7, tal como indica el issue.

## Revisiones humanas

Los conjuntos existentes de 300 temas y 345 pares fueron etiquetados por IA.
El evaluador conserva esa procedencia hasta importar decisiones humanas.
Una ejecución genera estos paquetes en el directorio de salida:

- `topic_review_packet.jsonl`: titulares y descripciones, propuesta y hash.
- `pair_review_packet.jsonl`: identidades de ambos artículos, propuesta y hash.
- `claim_review_packet.jsonl`: afirmación generada, citas, evidencia completa y hash.
- `benchmark_review_packet.jsonl`: consulta, expectativas propuestas, fuentes y hash del corpus para validar las etiquetas del benchmark.

El directorio indicado con `--human-reviews` debe contener `topics.jsonl`,
`pairs.jsonl` y `claims.jsonl`. También se acepta CSV con los mismos campos.
Para temas y pares, cada decisión tiene:

```json
{"subject_id":"ID del paquete","subject_hash":"hash del paquete","label":"etiqueta revisada","reviewer":"Nombre del revisor humano","reviewed_at":"2026-10-07T15:00:00-05:00"}
```

La etiqueta de tema es uno de los siete slugs del contrato. Para pares es
`0` (distinto), `1` (misma historia, distinto evento) o `2` (mismo evento).
Para afirmaciones se sustituye `label` por `verdict`, con `supported`,
`unsupported` o `unclear`, y se puede agregar `note`.

Para validar las expectativas propuestas del benchmark, agregar
`benchmark.jsonl` o `benchmark.csv` al directorio de revisiones, con
`subject_id`, `subject_hash`, `reviewer`, `reviewed_at` y `verdict: accepted`.
Una propuesta rechazada se reporta y requiere corregir y versionar el conjunto
de desarrollo; el paquete reservado permanece congelado. Si estas revisiones
no están disponibles, los resultados conservan su carácter provisional.

Los hashes vinculan la decisión al contenido exacto revisado, incluyendo las
fuentes de una afirmación. Una revisión de otro contenido no se aplica. Las
decisiones duplicadas o con IDs desconocidos se reportan; una etiqueta creada
por IA no cuenta como revisión humana. Repetir la misma afirmación no permite
alcanzar artificialmente la muestra de 30. El paquete de pares conserva las
identidades estables de los artículos, nunca usa los antiguos índices de fila
para evaluar.

## Pruebas T01–T10

El comando ejecuta toda la suite y guarda `pytest.xml` y `pytest.log`. La matriz
de aceptación referencia pruebas concretas y solo marca un caso como cumplido
si todos sus checks se ejecutaron y pasaron. T01 cubre fechas ausentes y nulos,
T02 procedencia de repeticiones, T03 recirculación, T04 período de datos
oficiales, T05 contradicciones, T06 abstención, T07 separación de instrucciones,
T08 puntajes explicados y control humano, T09 paquetes validados y T10 el
servidor real offline, reinicio y persistencia. La evidencia local de T10 se
guarda en `http-runtime.json`; la demo y su documentación en Notion pertenecen
a G10.
