# Operación

Guía para reconstruir datos, preparar modelos, evaluar y exportar.
Para arrancar la demo, ver el [README](../README.md#pruébalo-sin-red-o-con-ia-en-la-nube).

El paquete Python y el comando de consola conservan el identificador técnico `whoami`.

## Configuración y persistencia

Por defecto, la aplicación carga el corpus real procesado y las fichas de `outputs`.
Sin una clave de Gemini utiliza el modo offline; con una clave habilita generación verificable.
Para la demo sintética independiente, configurar `WHOAMI_DEMO=1` y `WHOAMI_OFFLINE=1`.
`--link-mode copy` en `uv sync` evita problemas de enlaces de archivos cuando el repositorio está en OneDrive.

Las decisiones humanas se guardan fuera del repositorio, en `%LOCALAPPDATA%/whoami/editorial.sqlite3` en Windows.
La ruta puede configurarse con `WHOAMI_DATABASE`.

La configuración opcional está documentada en [.env.example](../.env.example).
El servidor carga el `.env` existente sin sobrescribir variables explícitas del entorno.
No subir ese archivo al repositorio.
Consultar [la documentación del backend](backend.md) y [el editor G6](g6-editor.md) para configurar datos, persistencia, recuperación local y cuotas.

## Demo sin conexión

Ver [G10: modo offline](g10-offline.md).
`whoami offline-demo prepare --output offline-demo` congela el snapshot validado.
`whoami offline-demo serve --bundle offline-demo` lo verifica y fuerza el modo sin conexión, sin llamadas a Gemini ni carga de modelos locales.

## Datos y procesamiento

Las capturas originales se conservan en `data/raw/`.
Los archivos normalizados se escriben en `data/processed/` y sus hashes en `data/manifest.json`.
La reconstrucción del corpus funciona sin red a partir de las capturas guardadas:

```powershell
uv run --locked whoami build
```

Para actualizar fuentes concretas se necesita conexión:

```powershell
uv run --locked whoami ingest --only prensa,telemetro,panamaamerica
uv run --locked whoami ingest --only gdelt-gkg
uv run --locked whoami build
```

Seleccionar un medio con `--only` descarga su canal directo; GDELT se selecciona con sus propias claves.
El snapshot de GDELT GKG contiene seis lotes horarios multilingües y distingue las fechas de detección de las de publicación.
Su cobertura es parcial y queda registrada en `calidad_noticias.json`.
Los feeds de otros medios cubren principalmente los últimos dos días.

`uv run --locked whoami ingest --only gdelt` intenta recuperar los últimos 30 días mediante DOC 2.0, con cortes diarios.
Usa un timeout de 60 segundos, una separación mínima de 6 segundos y hasta cinco intentos con backoff.
Divide las consultas con 250 resultados y reanuda intervalos completos.
Puede tardar varios minutos ante respuestas HTTP 429; los fallos se conservan en `data/raw/news/gdelt/doc/`.
Ver [el cierre de G1](g1-completion.md) para la cobertura y los límites del corpus.

## Modelo de embeddings

Para instalar la revisión fijada de EmbeddingGemma desde una máquina nueva:

```powershell
uv run --locked whoami download-model
uv run --locked whoami download-model --offline
```

El segundo comando comprueba que los tres archivos están disponibles sin usar la red.
`--directory RUTA` permite elegir el directorio; para usarlo al procesar datos, definir `WHOAMI_EMBEDDING_MODEL_DIR` con esa misma ruta.
Una descarga incompleta puede reanudarse; cada archivo se instala tras copiarse por completo.

`whoami embed` construye los vectores locales y `whoami pipeline --sin-llm` procesa el corpus sin llamadas al modelo generativo.
`whoami generar` produce fichas y respuestas con el modelo configurado y requiere preparar sus entradas y credenciales.
Consultar las opciones con `uv run --locked whoami --help` y `uv run --locked whoami generar --help`.

## Cobertura de TVN y borradores

La comparación de cobertura distingue eventos ya cubiertos por TVN, posibles actualizaciones externas con datos nuevos citados, eventos sin coincidencia en el snapshot y novedad no comprobada.
Los grupos ya cubiertos se excluyen de la bandeja principal y de nuevas fichas.
Una ausencia en el snapshot no demuestra que TVN nunca haya publicado el evento; la cobertura incompleta se muestra al editor.
Las actualizaciones requieren verificar el alcance del dato nuevo.

Para escribir borradores, el modelo selecciona y ordena afirmaciones aceptadas.
El código conserva sus textos, tipos y atribuciones en título, brief, guion y copy, y comprueba sus referencias al cargar el paquete.
El registro de revisiones exporta también el contenido revisado y el historial de versiones retiradas.
Cambiar la ficha, el grupo o sus fuentes abre un nuevo ciclo de revisión.

## Validación y evaluación

```powershell
uv run --locked pytest -q
```

La suite cubre contratos, procesamiento, generación y revisión editorial.
Incluye el reinicio de un servidor HTTP real y la validación de los archivos exportados contra el contrato compartido.

Para ejecutar el benchmark G7, comparar BM25 con embeddings y guardar las métricas junto con todas las pruebas:

```powershell
uv run --locked whoami evaluar --mode recorded
```

El modo `live` mide la generación con Gemini.
Las consultas reservadas se mantienen fuera del repositorio.
Ver [la evaluación G7](evaluation.md) para requisitos, métodos y formatos, y [los resultados](evaluation-results.md).

## Exportación

Para exportar las fichas, consultas y decisiones del ciclo de revisión actual, detener primero el servidor y ejecutar:

```powershell
uv run --locked whoami export-backend --output outputs
```
