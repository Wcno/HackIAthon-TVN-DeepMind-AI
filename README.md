# TVN DeepMind AI

**De la señal a la decisión: copiloto de inteligencia informativa para TVN Media.**

TVN DeepMind AI es un prototipo desarrollado para la hackIAthon TVN Media que
transforma noticias públicas e indicadores oficiales en temas priorizados,
fichas de evidencia y borradores editoriales para revisión humana. Está pensado
para ayudar a editores, periodistas y productores digitales a planificar la
agenda, investigar hechos y preparar contenidos con fuentes trazables.

El foco editorial es descubrir noticias de otras fuentes que TVN todavía no
haya publicado. El archivo de TVN sirve como referencia de su cobertura: una
noticia ya publicada por TVN no cuenta como una novedad para el medio. Los
títulos deben captar la atención y comunicar el hecho con claridad y fidelidad.

El proyecto busca reducir el tiempo dedicado a revisar fuentes dispersas,
identificar noticias sobre un mismo evento y encontrar contexto relevante.
Cada resultado debe permitir revisar su evidencia, sus fechas y lo que falta
verificar antes de tomar una decisión editorial.

## Funcionalidades

- **Ingesta de fuentes públicas:** noticias de TVN y otros medios, GDELT,
  indicadores del Banco Mundial e INEC y eventos sísmicos de USGS.
- **Análisis y priorización:** clasificación temática, agrupación de noticias,
  detección de recirculación y puntajes explicados para organizar la agenda.
- **Contexto y evidencia:** vinculación de noticias con datos oficiales y
  fichas que reúnen fuentes, afirmaciones y preguntas pendientes.
- **Generación asistida:** borradores y respuestas a consultas en español con
  citas y verificaciones de respaldo en la evidencia.
- **Revisión humana:** registro de decisiones y versiones en SQLite; los
  cambios de contenido invalidan aprobaciones anteriores.
- **Demo sin conexión:** datos sintéticos y respuestas precalculadas para
  recorrer el flujo editorial sin una clave de API.

## Flujo editorial

1. Consultar la calidad y cobertura de los datos cargados.
2. Revisar la bandeja de temas priorizados.
3. Abrir un grupo de noticias y consultar su contexto oficial.
4. Examinar la ficha de evidencia y el borrador editorial.
5. Registrar la decisión del revisor humano.

La caja de consultas permite explorar respuestas con evidencia. En el modo
offline solo están disponibles las consultas precalculadas; una consulta nueva
muestra que no puede resolverse sin conexión. El prototipo no publica contenido
automáticamente.

## Tecnologías y estructura

El proyecto utiliza Python 3.12 o superior, FastAPI y Uvicorn para el servidor,
Jinja2 para las vistas, Pydantic para los contratos de datos y SQLite para la
persistencia editorial. El procesamiento incluye embeddings locales con
EmbeddingGemma en ONNX y generación con Gemini.

El paquete Python y el comando de consola conservan el identificador técnico
`whoami`, utilizado en las instrucciones de ejecución.

```text
src/whoami/
  ingest/       Captura y normalización de fuentes públicas
  pipeline/     Clasificación, agrupación, contexto y priorización
  generation/   Recuperación, generación y verificación de evidencia
  llm/          Cliente de modelos, caché y control de llamadas
  backend/      Vistas web, revisión humana y persistencia
data/           Capturas originales, corpus procesado y datos de demo
outputs/        Fichas, consultas y entregables generados
docs/           Requisitos, contratos, decisiones y documentación técnica
experiments/    Evaluaciones de modelos y estrategias de análisis
tests/          Pruebas del procesamiento y del flujo editorial
```

## Inicio rápido

Requisitos: Python 3.12 o superior y `uv`. Ejecutar desde la raíz del repositorio:

```powershell
uv sync --locked --link-mode copy
uv run --locked uvicorn whoami.backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Abrir [la bandeja editorial](http://127.0.0.1:8000/inbox). Por defecto, la
aplicación inicia con noticias sintéticas y consultas precalculadas, sin una
clave de Gemini. El corpus real se procesa por separado; esta demo inicial no
lo carga automáticamente. `--link-mode copy` evita problemas de enlaces de
archivos cuando el repositorio está en OneDrive.

Las decisiones humanas se guardan fuera del repositorio, en
`%LOCALAPPDATA%/whoami/editorial.sqlite3` en Windows. La ruta puede configurarse
con `WHOAMI_DATABASE`.

La configuración opcional está documentada en [.env.example](.env.example).
Para usarla, copiar el archivo a `.env`, ajustar sus valores y arrancar el
servidor con:

```powershell
uv run --locked --env-file .env uvicorn whoami.backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

El servidor no carga `.env` implícitamente. No subir ese archivo al repositorio.
Consultar [la documentación del backend](docs/backend.md) para configurar los
directorios del corpus real, el modo online y la integración de consultas.

## Datos y procesamiento

Las capturas originales se conservan en `data/raw/`; los archivos normalizados
se escriben en `data/processed/` y sus hashes en `data/manifest.json`. La
reconstrucción del corpus funciona sin red a partir de las capturas guardadas:

```powershell
uv run --locked whoami build
```

Para actualizar fuentes concretas se necesita conexión:

```powershell
uv run --locked whoami ingest --only prensa,telemetro,panamaamerica
uv run --locked whoami ingest --only gdelt-gkg
uv run --locked whoami build
```

Seleccionar un medio con `--only` descarga su canal directo; GDELT se selecciona
con sus propias claves. El snapshot de GDELT GKG contiene seis lotes horarios
multilingües y distingue las fechas de detección de las de publicación. Su
cobertura es parcial, registrada en `calidad_noticias.json`; los feeds de otros
medios cubren principalmente los últimos dos días.

`uv run --locked whoami ingest --only gdelt` intenta recuperar los últimos
30 días mediante DOC 2.0, con cortes diarios, timeout de 60 segundos,
separación mínima de 6 segundos y hasta cinco intentos con backoff. Divide las
consultas con 250 resultados y reanuda intervalos completos. Puede tardar varios
minutos ante respuestas HTTP 429; los fallos se conservan en
`data/raw/news/gdelt/doc/`. Ver [el cierre de G1](docs/g1-completion.md) para
la cobertura y los límites del corpus.

Para instalar la revisión fijada de EmbeddingGemma desde una máquina nueva:

```powershell
uv run --locked whoami download-model
uv run --locked whoami download-model --offline
```

El segundo comando comprueba que los tres archivos están disponibles sin usar
la red. `--directory RUTA` permite elegir el directorio; para utilizarlo al
procesar datos, definir `WHOAMI_EMBEDDING_MODEL_DIR` con esa misma ruta. Una
descarga incompleta puede reanudarse; cada archivo se instala tras copiarse por
completo.

El comando `whoami embed` construye los vectores locales y
`whoami pipeline --sin-llm` procesa el corpus sin llamadas al modelo generativo.
La primera descarga de EmbeddingGemma requiere conexión; después puede
reutilizarse el modelo en caché. `whoami generar` produce fichas y respuestas
con el modelo configurado y requiere preparar sus entradas y credenciales.
Consultar las opciones con `uv run --locked whoami --help` y
`uv run --locked whoami generar --help`.

La comparación de cobertura distingue eventos ya cubiertos por TVN, posibles
actualizaciones externas con datos nuevos citados, eventos sin coincidencia en
el snapshot y novedad no comprobada. Los grupos ya cubiertos se excluyen de la
bandeja principal y de nuevas fichas. Una ausencia en el snapshot no demuestra
que TVN nunca haya publicado el evento; la cobertura incompleta se muestra al
editor. Las actualizaciones requieren verificar el alcance del dato nuevo.

Para escribir borradores, el modelo selecciona y ordena afirmaciones aceptadas.
El código conserva sus textos, tipos y atribuciones en título, brief, guion y
copy, y comprueba sus referencias al cargar el paquete. El registro de revisiones
exporta también el contenido revisado y el historial de versiones retiradas;
cambiar la ficha, el grupo o sus fuentes abre un nuevo ciclo de revisión.

## Validación y exportación

```powershell
uv run --locked pytest -q
```

La suite cubre contratos, procesamiento, generación y revisión editorial;
incluye el reinicio de un servidor HTTP real y la validación de los archivos
exportados contra el contrato compartido.

Para ejecutar el benchmark G7, comparar BM25 con embeddings y guardar las
métricas junto con todas las pruebas:

```powershell
uv run --locked whoami evaluar --mode recorded
```

El modo `live` mide la generación con Gemini. Las consultas reservadas se
mantienen fuera del repositorio y las métricas con etiquetas de IA se marcan
como provisionales hasta incorporar las revisiones humanas. Ver
[la evaluación G7](docs/evaluation.md) para requisitos, métodos y formatos.

Para exportar las fichas, consultas y decisiones del ciclo de revisión actual,
detener primero el servidor y ejecutar:

```powershell
uv run --locked whoami export-backend --output outputs
```

## Documentación

- [Requisitos del reto](docs/challenge/INDEX.md): alcance, casos de uso,
  entregables y criterios de evaluación.
- [Decisiones del equipo](docs/challenge/00-decisiones-del-equipo.md): ventanas
  de datos y comportamiento de la demo offline.
- [Backend y revisión editorial](docs/backend.md): rutas, persistencia,
  configuración e integración.
- [Contrato de pantallas](docs/screen-contract.md): interfaz del flujo editorial.
- [Cobertura del corpus](docs/g1-completion.md): fuentes, calidad y evidencia.
- [Embeddings locales](docs/adr/0003-local-embeddings-embeddinggemma.md):
  propuesta técnica y evaluación del modelo.

Notion forma parte de los requisitos del reto para documentar decisiones,
pruebas y presentar el proyecto. El alcance y los entregables se describen en
la documentación del reto.

## Flujo de trabajo del equipo

La rama de integración y producción es `prod`. Cada cambio se desarrolla en una rama corta y se integra mediante un pull request hacia `prod`, con los checks configurados en verde. No se requiere una aprobación para fusionar. No usamos una rama `dev` en este flujo.

1. Actualizar `prod` y crear una rama para el cambio:

   ```bash
   git fetch origin
   git switch prod
   git pull --ff-only origin prod
   git switch -c feat/nombre-del-cambio
   ```

   Si aún no existe `prod` localmente, crearla con `git switch --track origin/prod`.

2. Implementar y probar el cambio; hacer commit y subir la rama:

   ```bash
   git add <archivos-del-cambio>
   git commit -m "feat: describir el cambio"
   git push -u origin feat/nombre-del-cambio
   ```

3. Abrir un pull request con destino a `prod`, explicando qué cambió y cómo probarlo.
4. Con los checks configurados en verde, hacer squash merge y eliminar la rama del cambio.
5. Desplegar la versión integrada en `prod` usando el proveedor que acuerde el equipo.

También se usan ramas `fix/nombre-del-arreglo` para correcciones. No se hacen pushes directos a `prod`.

### Configuración de GitHub y despliegue

- Usar `prod` como rama predeterminada.
- Proteger `prod`: exigir pull request y los checks configurados, sin aprobaciones obligatorias; aplicar la regla también a administradores e impedir force pushes y la eliminación de la rama.
- Exigir los checks de `G5 validation`: pruebas y build en Windows y Linux. La protección de rama debe configurarse en GitHub.
- Configurar el proveedor de despliegue para publicar desde `prod`; actualmente no hay un despliegue configurado.

Estas son las reglas acordadas. La protección, la rama predeterminada y el despliegue deben verificarse en sus respectivas plataformas.
