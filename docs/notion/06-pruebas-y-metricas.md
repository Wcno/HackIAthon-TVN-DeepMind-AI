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
| T10 · Sin internet durante la demo | Demo con el wifi apagado | Funcionar con snapshot y fallback documentado | **Parcial:** pruebas automatizadas pasan; **ensayo con el wifi apagado pendiente** | `test_smoke` (el pipeline offline no crea ningún LLM), `test_backend` (el proveedor nunca se llama sin conexión), `test_backend_process` (reinicio con la misma base) | Ensayar con el wifi apagado antes del pitch |

Un resultado «pasa» significa que la prueba se ejecuta y se cumple. No mide calidad con
datos reales. Las pruebas T07 y T10 en vivo siguen pendientes de ensayo manual.

## Métricas (§9.1)

Las cifras de esta tabla vienen del análisis G7 en `feat/g7-evaluation`, que todavía no
está integrado en `prod`. Son provisionales: las etiquetas humanas no se han revisado.

| Métrica | Meta | Resultado (G7, provisional) | n |
| --- | --- | --- | --- |
| Cobertura de citas | 100 % de afirmaciones factuales con evidencia identificable | 41/41 afirmaciones estructuradas; 21/21 respuestas | 41 + 21 |
| Validez de sustento | ≥ 90 % según revisión humana de ≥ 30 afirmaciones | **No medida: 0 afirmaciones revisadas por humanos** | 0 de 30 |
| Abstención correcta | ≥ 80 % de consultas sin respuesta | 7/7 | 7 |
| Abstención incorrecta | Registrar en preguntas respondibles | 1/27 respondibles rechazada (0/20 entre las sustentadas) | 27 |
| Corrección de consultas | Sin meta declarada | 37/40 (92,5 %); 6/6 en seguridad adversarial | 40 |
| Clasificación: macro-F1 | Reglas por palabras clave frente a embeddings | 0,451 frente a 0,804 | 300 etiquetas propuestas |
| Relación del mismo evento: F1 | Reglas frente a embeddings | 0,317 frente a 0,722 | 345 pares propuestos |
| Recuperación: Recall@8 | BM25 frente a embeddings | BM25 97,4 %; EmbeddingGemma 100 %; híbrido 100 % | 114 |
| Utilidad del ranking: P@5 | Exploratorio | **No medido** | — |
| Eficiencia | Mediana ≤ 15 s; reportar p95 y tokens | Mediana 1,42 s; p95 2,93 s; 46.280 tokens de red | 40 consultas |

Lectura honesta: BM25 ya recupera casi toda la evidencia esperada y es mucho más rápido.
Los embeddings ganan en clasificación y en agrupación, pero también generan más falsas
agrupaciones. Los resultados no justifican usar IA en cada tarea.

**Cifra de corpus:** las métricas G7 usan 2.941 noticias; el manifest actual tiene 3.176
incluidas. No deben citarse juntas hasta conciliarlas (ver `03-catalogo-de-datos.md`).

## Baselines (§8)

1. **Clasificación temática:** palabras clave frente a embeddings (macro-F1).
2. **Recuperación:** BM25 frente a embeddings e híbrido (Recall@8).

Dónde la IA no ayuda: BM25 gana en cifras exactas y siglas, y en velocidad.

## Pendientes antes de citar cifras ante el jurado

- Revisión humana de al menos 30 afirmaciones (sustento ≥ 90 %).
- Revisión de las etiquetas de tema y de pares.
- P@5 con el criterio de una persona editora, no de un agente.
- Integrar `feat/g7-evaluation` en `prod`, o citar solo lo que esté en `prod`.
- Conciliar 3.176 noticias incluidas con 2.941 de la evidencia.
