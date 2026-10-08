# Plan y decisiones

> Espeja la página «Plan y decisiones» del §5: al menos 8 tareas y 3 decisiones justificadas,
> registradas durante la ejecución. El historial de commits y de pull requests de este
> repositorio es la evidencia de que se registró sobre la marcha.

## Backlog

Estados: `hecho` · `en curso` · `pendiente` · `bloqueado`

| # | Tarea | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Corpus de noticias: TVN, GDELT DOC y GKG, Prensa, Telemetro, Panamá América | hecho | PR #35 (`cde4dff`) |
| 2 | Contrato de datos compartido y revisión de la fase de datos | hecho | PR #32 |
| 3 | Agrupación, clasificación temática y puntaje (G3) | hecho | PR #34 (`77474db`) |
| 4 | Generación con citas verificadas y consultas precalculadas (G4) | hecho | PR #34 |
| 5 | Backend editorial, persistencia y exportación (G5) | hecho | `92359ec` · `docs/review-g5.md` |
| 6 | Enfoque del README en TVN DeepMind AI | hecho | PR #36 (`16bf92c`) |
| 7 | Diseño visual final de las pantallas (G6) | pendiente | — |
| 8 | Evaluación reproducible con benchmark y revisión humana (G7) | en curso | rama `feat/g7-evaluation`, sin integrar |
| 9 | Páginas de Notion (este issue, G8) | en curso | `docs/notion/` |
| 10 | Revisión humana de etiquetas y afirmaciones | pendiente | — |
| 11 | Ensayo del pitch con el wifi apagado | pendiente | — |
| 12 | Despliegue en una capa gratuita | pendiente | depende de G6 |

## Decisiones

### D-01 · Modalidad editorial TVN

Se eligió la modalidad editorial porque el §1 la recomienda y porque la bancaria exige
una cuarta fuente (SBP) en PDF sin verificar. La editorial reutiliza fuentes que ya
están integradas y medidas.

### D-02 · Gemini para generación, modelo local para embeddings

- Generación con `gemini-3.5-flash-lite` (ADR-0001). Se descartó `gemini-3.8-flash`: en el
  humo, respondió 503 y tardó 268 s en el reintento, frente a unos 2 s de flash-lite.
- Embeddings: el tier gratuito de Gemini cuenta cada texto, unos 100 por minuto y 1.000 por
  día. El corpus de 2.941 noticias necesitaba tres días de cuota. ADR-0003 propone
  `embeddinggemma-300m` en ONNX q4 (nDCG@10 de 0,859 contra 0,887 de `gemini-embedding-2`),
  que corre sin internet y es necesario para T10. **Estado: propuesto, no aceptado.**

### D-03 · Verificación determinista de citas antes de mostrar cualquier afirmación

Cada afirmación debe citar un ID de evidencia existente, con un pasaje que aparezca
literalmente en el campo citado, y cualquier cifra debe estar en la evidencia tras
normalizar el formato numérico en español. Si una afirmación falla, se marca como «sin
sustento» y no se oculta. Así se cumple el §7 y la meta de cobertura de citas, y el jurado
puede comprobarlo en pantalla.

### D-04 · Ventana de noticias de 30 días previos al corte

Las noticias usan los 30 días previos al corte (D-04 del equipo), dentro del límite exterior
de 2025-10-02 (D-02). Los 30 días dan 3.176 noticias incluidas. Los indicadores del Banco
Mundial conservan 2010-2024 por ser series anuales. Los sismos del USGS usan la ventana
desde 2025-10-02 (D-02).

## Hallazgos que corrigieron el plan

- **Las pruebas de Windows fallaron por la codificación.** Se corrigió leyendo y escribiendo
  en UTF-8 explícito (`c9d95b6`). Es la prueba fallida y su corrección que pide el jurado.
- **La recirculación no se disparaba con datos reales.** G1 descarta las noticias viejas
  reeditadas por su fecha original; la regla de recirculación queda cubierta por pruebas.
- **La cuadrícula del Banco Mundial del §6 no cuadra.** 6 países × 6 indicadores × 15 años
  son 540 combinaciones, no 1.350. Se reporta 540 y se documenta la discrepancia.
- **Gemma no sirve para respuestas largas.** Tuvo cerca de un 20 % de JSON inválido y
  errores HTTP 500. Por eso generación usa flash-lite y Gemma solo queda para tareas cortas
  (temas, veredictos de agrupación, contradicciones).

## Pendiente de decidir

- Asignación nominal de los tres carriles.
- Fecha y hora del pitch.
- Qué proveedor gratuito se usará para el despliegue.
