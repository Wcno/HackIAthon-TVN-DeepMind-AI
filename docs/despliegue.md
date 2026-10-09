# Despliegue: VPS de Oracle con Dokploy

El `Dockerfile` construye la aplicación en línea: generación con Gemini, búsqueda
híbrida con el modelo EmbeddingGemma q4 fijado (se descarga al construir, unos
210 MB) y las ediciones y revisiones humanas en SQLite. Ejecuta `whoami local-demo`,
que no arranca sin clave de Gemini ni con búsqueda solo BM25: un despliegue roto
falla el chequeo de salud en vez de servir una app degradada.

El lockfile trae ruedas de Linux para x86_64 y aarch64, así que la imagen se
construye en las dos formas de Oracle (AMD y Ampere). Un límite de 512 MB de
memoria no alcanza para el modelo local ([spike](research/local-embeddings-spike.md)).

## Aplicación en Dokploy

1. **Origen:** este repositorio, rama `prod`, tipo de construcción **Dockerfile**
   (ruta `Dockerfile`, contexto `.`).
2. **Environment:** `GEMINI_API_KEY=<clave>`. Opcionales:
   `WHOAMI_GENERATION_DAILY_LIMIT` (pedidos al proveedor por día; la app gasta como
   máximo el 40 %, 200 por defecto) y `WHOAMI_EMBEDDING_THREADS` (2 por defecto).
3. **Volumen:** un volumen con nombre montado en `/data`. Guarda
   `editorial.sqlite3`; sin él, cada redespliegue pierde borradores y revisiones.
4. **Dominio:** puerto del contenedor `8000`, HTTPS con Let's Encrypt.

El primer arranque tarda unos segundos en cargar el modelo. El chequeo de salud
consulta `/demo-readiness`, que informa `"ready": true` y el modo de búsqueda sin
exponer la clave ni rutas.

## Acceso

La app no tiene inicio de sesión. Cualquiera con el enlace puede editar borradores,
registrar revisiones y gastar la cuota diaria de Gemini; el tope diario limita ese
gasto. Para restringirla, agregar Basic Auth a la aplicación en Dokploy.
