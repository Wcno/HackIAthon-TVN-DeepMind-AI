# Editor G6 conectado

El Borrador permite editar texto, añadir o quitar preguntas y verificaciones, descartar cambios y guardar explícitamente.
Las sugerencias del asistente nunca modifican el documento hasta elegir Aplicar.
Nada se publica automáticamente.

## Arranque y datos

```sh
uv sync --locked
WHOAMI_EMBEDDING_THREADS=2 uv run --locked uvicorn whoami.backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Abrir `/inbox` y la pestaña Borrador de una ficha.
El arranque carga `data/processed` y `outputs`, con 3.713 evidencias y cinco fichas en la entrega actual.
El `.env` existente se lee sin sobrescribir variables explícitas del entorno.
Con `GEMINI_API_KEY` hay generación online; sin clave, o con `WHOAMI_OFFLINE=1`, solo se usan respuestas precalculadas y caché.
Para la demo sintética independiente usar `WHOAMI_DEMO=1 WHOAMI_OFFLINE=1`.
Las bases de datos predeterminadas de demo y corpus real son distintas.

## Guardado y revisión

Los cambios humanos se guardan en una capa SQLite separada de las fichas estrictas del pipeline.
Guardar exige la versión actual, evita sobrescribir otra edición y revoca una aprobación anterior.
Las decisiones humanas corresponden a la versión de contenido revisada.
La interfaz protege la navegación cuando quedan cambios sin guardar.
Añadir una fuente no guarda ni publica el documento.
El asistente recibe también las fuentes seleccionadas aún sin guardar, siempre que existan en el corpus.
La interfaz no incluye historial de versiones ni avisos automáticos de cifras sin respaldo.
La validación de cifras y citas de las respuestas del modelo sigue activa en el backend.

## Recuperación y generación

La búsqueda recorre el corpus cargado, nunca la web en vivo.
La recuperación combina BM25 y los vectores existentes de `embeddinggemma-300m-q4` mediante fusión de rankings.
Solo las consultas se codifican localmente, en CPU, con el mismo modelo y prefijos del corpus.
El umbral semántico de recuperación y del benchmark es 0,62; BM25 también recupera evidencias oficiales sin vector.
En consultas de texto libre, la puerta de entrada al generador usa 0,43 para admitir preguntas breves.
Superar esa puerta no garantiza una respuesta: siguen vigentes las comprobaciones de evidencia, cifras y citas y la abstención cuando no hay sustento.
Se validan manifiesto, revisión, dimensiones y hashes antes de cargar el modelo.
Si los archivos locales no están disponibles o son incompatibles, se degrada a BM25 sin descargar archivos ni llamar embeddings cloud.
La demo usa BM25 sin inicializar el modelo local.
El modelo se prepara por separado mediante el flujo de embeddings documentado en ADR-0003.

Gemini recibe un esquema estricto específico para la acción, con IDs de fuentes permitidos.
Cada respuesta o propuesta requiere citas literales verificables, y las cifras se contrastan con esas citas.
Resultados inválidos no se guardan en caché ni se aplican al borrador.
La caché incluye el contexto, las fuentes, el esquema y la versión del prompt.
El asistente muestra errores controlados y permite reintentar manualmente.

## Cuota compartida

Las llamadas de generación usan el ledger compartido y reservas SQLite persistentes antes de cada intento.
Se cuentan reintentos, errores y reservas pendientes; la caché y el modo offline no consumen cuota.
Los límites RPM y TPM incluyen llamadas recientes registradas por otros procesos.
El presupuesto es el menor entre el cap experimental existente y el 40% de la cuota diaria del proveedor.
Para Flash Lite se usa la cuota de 500 solicitudes por día documentada en ADR-0001, manteniendo el cap experimental más estricto de 100 para 3.5.
Esto reserva al menos el 60% de la cuota del proveedor frente al gasto observado y autorizado por este editor.
Si AI Studio muestra una cuota diferente, configurar `WHOAMI_GENERATION_DAILY_LIMIT`.
Todos los workers del editor deben compartir `WHOAMI_LEDGER` y `WHOAMI_GENERATION_QUOTA_DB`.
El presupuesto se reinicia según el día de cuota de Google, salvo `WHOAMI_BUDGET_SINCE` explícito.
La cuota agotada falla sin realizar una llamada externa.

Las reservas son atómicas entre workers del editor.
Otros clientes independientes del proyecto no reservan en esta SQLite; sus llamadas registradas se contabilizan, pero sus llamadas simultáneas aún sin registrar no pueden observarse.
El límite no sustituye la supervisión de AI Studio ni garantiza el gasto de herramientas externas que ignoren el ledger.

## Exportación

Detener el servidor antes de ejecutar `uv run --locked whoami export-backend --output outputs`.
Los contratos estrictos del pipeline no se flexibilizan para admitir preguntas humanas variables.
Cuando hay ediciones, `borradores_editoriales.jsonl` conserva los borradores humanos, fuentes, versiones y revisiones del contenido actual.
Las fichas estrictas exportadas conservan el seed del pipeline, sin adjudicarle aprobaciones de contenido humano distinto.
Las aprobaciones de los borradores editados quedan exclusivamente en el archivo complementario.
Sin ediciones, se mantienen los tres archivos de exportación existentes.
Los archivos se reemplazan atómicamente de forma individual, no como una transacción multifichero.

## Verificación

```sh
uv run --locked pytest -q
uv run --locked pytest tests/test_editor.py tests/test_editor_browser.py tests/test_editor_quota.py tests/test_editor_retrieval.py tests/test_editor_export.py -q
```

Las pruebas HTTP usan SQLite temporal y transporte Gemini simulado.
Las pruebas Playwright recorren guardado, recarga, aplicación explícita, fuentes, navegación protegida, portapapeles y móvil offline.
Instalar Chromium con `uv run playwright install chromium` si no existe un navegador compatible.
El cierre se verificó con 754 pruebas aprobadas, navegador desktop/móvil con datos reales y una sugerencia Gemini real con tres opciones citadas, sin cambios automáticos.
No se realizaron llamadas cloud de embeddings.
