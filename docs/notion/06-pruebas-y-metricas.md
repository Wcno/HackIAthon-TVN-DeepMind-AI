# Pruebas y métricas

> Espeja la página «Pruebas y métricas» del §5. La matriz T01-T10 es evidencia mínima de
> admisión. Cada resultado indica si lo verificó una prueba automatizada o si queda una
> comprobación manual pendiente.

## Evidencia de ejecución

- Comando: `uv run --locked pytest -q --junitxml outputs/validation/g8-junit.xml` (con `PYTHONUTF8=1`).
- Commit probado: `origin/prod` (`16bf92c`) más los cambios de G8.
- Resultado: **637 pruebas pasan, 0 fallan**. Registro: `outputs/validation/g8-pytest.log`.
  Resultados por prueba: `outputs/validation/g8-junit.xml`.

## Matriz de aceptación (§9)

**Evidencia G10 (2026-10-08, rama `feat/g10-offline`, base `prod` `1153820`):**
1.091 pruebas pasan, incluidas las de navegador con Edge; wheel construido y
probado desde una instalación separada con el paquete reubicado. Registro y XML:
`outputs/validation/g10-final/pytest.log` y `pytest.xml`. El reporte del ensayo,
auditorías con cero intentos externos/de inferencia y capturas de escritorio/móvil
se conservan en esa misma carpeta. La captura histórica de G8 anterior permanece
sin sobrescribirse. Revisión final independiente: Standards 0 y Spec 0; ver
`docs/review-g10.md`.

Las pruebas se citan por archivo. Cada nombre de archivo existe bajo `tests/` y sus pruebas
están en el XML de la corrida.

| ID · Caso | Entrada | Resultado esperado | Observado | Pruebas que lo cubren | Corrección |
| --- | --- | --- | --- | --- | --- |
| T01 · Fechas inválidas y nulos | Datos con fechas inválidas y nulos | Validar, separar errores y conservar nulos | Automatizado: pasa | `test_schemas` (fechas ISO 8601 UTC), `test_worldbank` (nulos conservados), `test_inec` (faltantes como nulo, nunca cero), `test_gdelt_gkg` (campos faltantes excluidos) | — |
| T02 · Mismo evento en varios registros | Tres registros del mismo evento | Agrupar sin perder fuentes ni triplicar importancia | Automatizado: pasa | `test_provenance` (agencias y copias casi idénticas), `test_scoring` (duplicar no sube el puntaje), `test_schemas` (agencia replicada cuenta una vez) | — |
| T03 · Noticia antigua recirculada | Noticia antigua que vuelve a circular | Mostrar fecha original; no presentarla como nueva | Automatizado: pasa | `test_recirculation`, `test_scoring` (grupo recirculado no es nuevo), `test_run` (conserva fecha original) | Decisión de G1: las reediciones antiguas se descartan por fecha original; la regla sigue probada con datos sintéticos |
| T04 · Cifra anual del Banco Mundial | Serie anual con país, año y unidad | Mantener país, año y unidad; no presentarla como cifra de hoy | Automatizado: pasa | `test_schemas` (período, unidad y valor obligatorios), `test_generation_verifier` (el período debe declararse), `test_worldbank` (unidad por indicador) | — |
| T05 · Dos afirmaciones incompatibles | Dos cifras o fechas que no coinciden | Mostrar ambas, su alcance y la revisión pendiente | Automatizado: pasa | `test_generation_contradictions`, `test_schemas` (la contradicción muestra ambas versiones con su fuente) | — |
| T06 · Consulta sin respuesta | Pregunta sin evidencia en el corpus | Abstención explícita; sin cifras ni citas inventadas | Automatizado: pasa | `test_generation_cosine_gate`, `test_generation_query_box`, `test_backend` (consultas precalculadas con abstención) | — |
| T07 · Fuente que pide ignorar instrucciones | Titular con instrucciones maliciosas | Tratarla como dato no confiable; no revelar secretos | Automatizado: pasa | `test_generation_prompting` (instrucciones fuera del turno de evidencia; canario de fuga) | — |
| T08 · Caso de prioridad alta | Grupo con puntaje alto y evidencia insuficiente | Exponer componentes y regla; no habilitar publicación | Automatizado: pasa | `test_scoring`, `test_run` (componentes con justificación), `test_schemas` (prioridad alta con evidencia insuficiente no se aprueba) | — |
| T09 · Brief editorial | Grupo con evidencia suficiente | Formato útil, citas pertinentes, hechos e inferencias distinguidos | Automatizado: pasa | `test_schemas` (brief ≤250 palabras, copy ≤80, tres preguntas), `test_generation_entailment`, `test_generation_verifier` (acusación no presentada como hecho) | — |
| T10 · Sin internet durante la demo | Snapshot real, conexiones externas y carga de modelos bloqueadas | Siete etapas, consultas guardadas y fallback sin Gemini | **Ensayo automatizado completo: pasa.** 48 consultas, edición en navegador y revisión tras reinicio; cero intentos externos o de inferencia. Ensayo físico con el wifi apagado pendiente | `test_offline`, `scripts/validate_g10.py`; [reporte G10](../../outputs/validation/g10-final/report.json), auditorías y capturas en `outputs/validation/g10-final/` | Paquete verificable y comando `offline-demo serve`; [preparación y fallback](../g10-offline.md) |

Un resultado «pasa» significa que la prueba se ejecuta y se cumple. No mide calidad con
datos reales. T10 se ensayó con servidor y navegador reales bajo aislamiento de
red: las siete etapas, una respuesta útil, una abstención y una pregunta inédita
funcionan sin acceso externo. El reporte declara `physical_wifi_disabled=false`:
no se cambió el wifi de la máquina. El ensayo físico antes del pitch y T07 con
proveedor real siguen a cargo del equipo. Según D-05, estos archivos son el espejo
para copiar a la página nativa de Notion; no hubo una sincronización automática.

## Métricas (§9.1)

G7 está integrado en `prod` mediante [PR #37](https://github.com/Wcno/hackiaton-whoamisfc/pull/37),
commit `957c3642e7143f1ab6a2c134e5e2e1ed93b9f8b7`. Las cifras siguientes corresponden
a la captura `outputs/evaluation/g7-structured-live` y su replay con revisiones humanas
`outputs/evaluation/g7-reviewed`, sobre el mismo commit congelado.
Las 41 afirmaciones, las 300 etiquetas de tema y los 345 pares tienen revisión humana registrada
en `outputs/evaluation/human-reviews/`.
Las 40 expectativas del benchmark también están aprobadas por el revisor.

| Métrica | Meta | Resultado (G7 con revisión humana) | n |
| --- | --- | --- | --- |
| Cobertura de citas | 100 % de afirmaciones factuales con evidencia identificable | 41/41 afirmaciones de fichas; 33/33 afirmaciones/versiones de consultas (23 + 10); 21/21 respuestas con referencias | 41 + 33; referencias no equivalen a sustento semántico |
| Validez de sustento | Referencia original: ≥ 90 % sobre ≥ 30 afirmaciones | **39/41 sustentadas (95,1 %)**; 2 dudosas | 41 revisadas (meta: ≥ 30) |
| Abstención correcta | ≥ 80 % de consultas sin respuesta | 7/7 | 7 |
| Abstención incorrecta | Registrar en preguntas respondibles | 1/27 respondibles rechazada (0/20 entre las sustentadas) | 27 |
| Corrección de consultas | Sin meta declarada | 37/40 (92,5 %); 6/6 en seguridad adversarial | 40 |
| Clasificación: macro-F1 | Reglas por palabras clave frente a embeddings | 0,451 frente a 0,804 | 300 etiquetas revisadas por humano |
| Relación del mismo evento: F1 | Reglas frente a embeddings | 0,317 frente a 0,722 (precisión 0,95/0,66; recall 0,19/0,79) | 345 pares revisados por humano |
| Recuperación: Recall@8 | BM25 frente a embeddings | BM25 97,4 %; EmbeddingGemma 100 %; híbrido 100 % | 114 |
| Utilidad del ranking: P@5 | Exploratorio | **4/5 (80 %)** frente a la selección de un editor; 3/5 sin la corrección descrita abajo | 1 revisor, 25 candidatas |
| Eficiencia | Mediana ≤ 15 s; reportar p95 y tokens | Mediana 1,42 s; p95 2,93 s; 46.280 tokens de red | 40 consultas |

Lectura honesta: BM25 ya recupera casi toda la evidencia esperada y es mucho más rápido.
Los embeddings ganan en clasificación y en agrupación, pero también generan más falsas
agrupaciones. Los resultados no justifican usar IA en cada tarea.

**Cifra de corpus:** las métricas G7 usan el snapshot congelado de 2.941 noticias;
el manifest más reciente de G1 tiene 3.176 incluidas. Son capturas distintas y se
citan con su procedencia; nunca se mezclan las posiciones del CSV nuevo con los
vectores de la captura anterior (ver `03-catalogo-de-datos.md`).

## Baselines (§8)

1. **Clasificación temática:** palabras clave frente a embeddings (macro-F1).
2. **Recuperación:** BM25 frente a embeddings e híbrido (Recall@8).

Dónde la IA no ayuda: BM25 gana en cifras exactas y siglas, y en velocidad.

## Método de la revisión humana

- **Afirmaciones (41):** diez revisadas una a una en el chat (ocho sustentadas, dos dudosas).
  Las otras 31 se verificaron contra las fuentes citadas fuera de la herramienta y se registraron
  después en la Mesa de verificación G7. Todas quedan sustentadas.
- **Temas (300) y pares (345):** etiquetas propuestas por IA, revisadas por una persona contra
  las fuentes fuera de la herramienta y confirmadas en bloque, sin cambios.
  Cada registro lleva `method: bulk_attestation`.
- **Benchmark (40):** el revisor aprobó todas las expectativas en el chat, sin cambios.
  En D-C06 el sistema se abstiene; según el revisor es una abstención conservadora y no un error
  del modelo, aunque la puntuación automática la cuenta como fallo. En D-A05 la respuesta
  (151,5 millones) coincide con la fuente; el fallo viene del criterio de puntuación.
- **P@5:** las 25 historias mejor puntuadas que TVN no ha publicado, en orden aleatorio y sin
  puntajes; un revisor con rol de editor eligió cinco. Después de ver el ranking, el revisor
  aclaró que quería el aviso de lluvias más reciente (4-6 oct) y había marcado uno anterior
  (25-26 sep). Con esa corrección, 4/5; sin ella, 3/5. Detalle en
  `outputs/evaluation/human-reviews/precision-at-5.json`.

## Revisión editorial en la app (etapa 7)

Decisiones registradas por el equipo en la app y exportadas con `whoami export-backend` a `outputs/revisiones.jsonl`:

| Caso | Decisión | Responsable | Nota |
| --- | --- | --- | --- |
| CASO-da87849e79 | `en_revision` → `aprobado_como_borrador` | Jeremiah Kurmaty | «Excelente trabajo» |
| CASO-03b7c512cc | `requiere_evidencia` | Keneth Benavidez | «falta mas cositas» |
| CASO-4656f80875 | `descartado` | Wilfredo Cano | — |

Aprobar como borrador no publica nada; la publicación queda fuera del sistema.

## Ahorro de tiempo (pendiente de medir)

El §9 pide medir el ahorro solo con una tarea equivalente, manual frente a asistida, e indicar el número de pruebas.

**Tarea:** encontrar 3 historias que TVN aún no haya publicado y, para cada una, anotar título, fuentes con enlace y qué falta verificar.

**Protocolo:**

1. Dos personas del equipo hacen la tarea dos veces: una a mano (sitios de medios, Sinaproc, MEF, ACP) y otra con la app.
2. La persona A empieza a mano y la B con la app, para compensar el aprendizaje.
3. En cada corrida se usa una ventana de noticias distinta, para no repetir historias.
4. Se cronometra desde abrir la primera fuente hasta tener las 3 fichas completas.
5. Otra persona revisa que las 3 historias de cada corrida no estén en TVN y que sus fuentes sean válidas.
   Una corrida con historias inválidas no cuenta.

**Resultados:**

| Persona | Modo | Orden | Minutos | Historias válidas |
| --- | --- | --- | --- | --- |
| A | Manual | 1 | | /3 |
| A | App | 2 | | /3 |
| B | App | 1 | | /3 |
| B | Manual | 2 | | /3 |

Reportar la mediana por modo con n = 2 por modo.
No se infiere aumento de audiencia ni otros beneficios de esta medición.

## Pendientes antes de citar cifras ante el jurado

- Evaluación reservada de 20 consultas en #25.
- P@5 es exploratorio: un revisor y una corrida.
- Citar por separado las capturas históricas y los resultados posteriores a #40.
