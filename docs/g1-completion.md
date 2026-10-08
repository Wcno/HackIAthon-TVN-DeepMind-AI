# G1 · Datos de GDELT y corpus de varios medios

Issue de desarrollo: [G1 #19](https://github.com/Wcno/hackiaton-whoamisfc/issues/19).
El handoff recibido corresponde a G1; la issue de GitHub #1 documenta el flujo de PRs.
Base de revisión: `origin/prod`, fijada en `92359ec93d9e7bc665281949f3890cdc70237cf0`.
Durante el desarrollo se integró el nuevo `prod` de G3/G4
(`77474db4ff9b30f2ee26f4df292be6418f339fa1`); la revisión final compara contra esa base.
Fecha de trabajo: 7 de octubre de 2026, Panamá (8 de octubre en UTC).

## Resultado

El corpus conserva titulares reales de GDELT GKG, sin depender de una respuesta
exitosa de DOC durante la demo. Se añadieron capturas directas de La Prensa,
Telemetro y Panamá América, y se regeneraron los archivos del contrato y el
manifest. TVN, las seis entidades oficiales, Banco Mundial, USGS e INEC conservan
su normalización previa. D-04 fija la ventana de noticias en 30 días; D-02 sigue
aplicando a USGS y Banco Mundial conserva 2010–2024.

GDELT DOC admite descarga reanudable, cortes diarios y subdivisión al alcanzar
250 filas. Cada intento conserva bytes, URL, hora UTC, estado, latencia, tamaño,
SHA-256 y error. Los 429 no se interpretan como datasets vacíos ni se reutilizan
como intervalos completos. El backoff parte de 30 segundos y respeta un
`Retry-After` numérico mayor; se detiene tras cinco intentos fallidos.

GKG usa el flujo **multilingüe** `translation.gkg.csv.zip`. La exploración anterior
del flujo original en inglés no permitía evaluar la cobertura de los medios en
español. El [codebook oficial de GKG 2.1](https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf)
documenta el formato tabulado, URL y bloque XML adicional. El parser recupera
`PAGE_TITLE` del XML y atribuye cada URL a su dominio exacto. La fecha del lote
se conserva como detección; no se utiliza como publicación ni se infiere una
publicación desde el slug. Cuando el feed directo aporta publicación, esa fecha
manda el filtro de ventana; una detección reciente no rescata noticias antiguas.

## Cobertura y evidencia

Se conservaron los seis ZIP originales de las 18:00, 19:00, 20:00, 21:00, 22:00
y 23:00 UTC del 7 de octubre: 45.043.334 bytes. Es una muestra **horaria parcial**,
no todas las actualizaciones de 15 minutos ni una cobertura continua de 30 días.
El reporte distingue GDELT DOC de GKG y enumera los lotes de GKG capturados.

El snapshot inicial de esta integración tiene 3.176 noticias incluidas y 41
noticias con origen GKG: La Prensa 10, Telemetro 8, Panamá América 2, Día a Día 14
y RPC TV 7. De esas 41, 19 se fusionan con el feed directo por URL y 22 conservan
publicación desconocida. `fecha_deteccion` permanece informada en ambas clases.
Los recuentos finales y exclusiones están en `data/processed/calidad_noticias.json`.

La cobertura del mismo evento en medios distintos de TVN queda demostrada por:

| Evento | Medio | ID del corpus | URL |
| --- | --- | --- | --- |
| Audiencia de Enrique Lau Cortés | La Prensa | `N-a6f2bb0fa295` | [Artículo](https://www.prensa.com/judiciales/enrique-lau-es-conducido-ante-un-juez-de-garantias-para-la-imputacion-de-cargos/) |
| Audiencia de Enrique Lau Cortés | Telemetro | `N-c89a3928fe51` | [Artículo](https://www.telemetro.com/nacionales/enrique-lau-cortes-juez-legaliza-aprehension-del-exdirector-la-css-n6094361) |
| Audiencia de Enrique Lau Cortés | Panamá América | `N-095a7b20f510` | [Artículo](https://www.panamaamerica.com.pa/judicial/juez-de-garantias-legaliza-aprehension-de-enrique-lau-cortes-1267191) |

Estos artículos satisfacen el criterio de varios medios sobre un mismo evento;
no prueban por sí solos independencia de procedencias. Esa evaluación editorial
corresponde a CU-03/T02 y al carril posterior de agrupación y evidencias.

## Reproducibilidad

```powershell
uv run --locked whoami ingest --only prensa,telemetro,panamaamerica
uv run --locked whoami ingest --only gdelt-gkg
uv run --locked whoami build
uv run --locked python scripts/validate_g1.py
uv run --locked pytest -q
uv build --wheel --out-dir dist
```

La demo usa únicamente el snapshot. Repetir `build` debe producir los mismos
bytes mientras el crudo no cambie. Los ZIP y las respuestas HTTP no se normalizan
al entrar en Git (`data/raw/** -text`). El escritor JSON fuerza LF para mantener
los hashes idénticos en Windows y Linux. Se restauraron desde los blobs originales
17 archivos previos cuyos hashes habían cambiado en este checkout por la conversión
automática a CRLF; no se volvió a consultar esas fuentes ni se cambió su contenido.

El manifest conserva la ubicación estable del contrato del proyecto,
`data/manifest.json`, y publica una copia idéntica en `data/processed/manifest.json`
para cumplir también la ubicación pedida por la issue. La copia se excluye de
sus propios hashes, para evitar una referencia circular.

El contrato G3 de miembros agrupados exige publicación. Su cargador informa y
omite las 22 filas sin publicación al agrupar; siguen disponibles en el CSV G1
y como evidencia con fecha nula y detección explícita. Los otros 19 registros
GKG tienen publicación obtenida del medio y son utilizables por G3. Tras cambiar
el corpus, G3 debe regenerar sus vectores con `whoami embed` antes de ejecutar
`whoami pipeline`; sus artefactos precalculados previos no son el nuevo corpus.

Validación final sobre el `prod` actualizado: 635 pruebas pasan y 2 se omiten
en Python 3.12, el wheel se construye, y el validador
offline confirma dos reconstrucciones idénticas, los 55 hashes de crudo y todos
los hashes procesados. Evidencia: `outputs/validation/g1-runtime.json`.
El test del límite de reintentos del backend conserva la respuesta 429 y el
`Retry-After` de una hora, con un plazo de 0,5 segundos para permitir la
inicialización del SDK 3 en Windows. No se cambió el plazo del backend en producción.
