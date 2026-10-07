# Contrato entre carriles: pantallas y datos (G2)

Qué muestra cada pantalla, qué datos necesita y quién los produce. Los esquemas están en código:
`src/whoami/schemas.py` (validan al construirse), vocabularios y rutas en `src/whoami/contracts.py`, lectura y
escritura en `src/whoami/store.py`.

## Carriles y archivos

```text
G1 ingest ──▶ data/processed/noticias.csv, indicadores.csv, indicadores_inec.csv, eventos.geojson,
              fuentes.json, calidad_*.json, data/manifest.json                       (ya existen)
G3 ai     ──▶ data/processed/grupos.jsonl      Grupo: miembros, puntaje, contexto oficial
              data/processed/evidencias.jsonl  Evidencia: todo lo que se puede citar
G4 ai     ──▶ outputs/fichas.jsonl             Ficha: §7
              outputs/consultas.jsonl          Respuesta: consultas precalculadas (offline, D-01)
G5 api    ──▶ outputs/revisiones.jsonl         RegistroRevision: historial de decisiones humanas
G6 front  ◀── lo lee todo mediante la API de G5
```

Mientras G3 y G4 no existen, **`data/demo/` contiene un conjunto sintético con los mismos archivos y esquemas**.
La interfaz cambia entre datos reales y de demostración cambiando un directorio:

```python
from whoami.contracts import DEMO
from whoami.store import cargar

paquete = cargar(DEMO)   # demo sintético; cargar() lee el pipeline real (processed/ y outputs/)
paquete.grupos           # tuple[Grupo, ...] ya en el orden de la bandeja
paquete.evidencias       # dict[id_evidencia, Evidencia]
```

`uv run whoami demo` regenera `data/demo/`. Las noticias de la demostración son inventadas (`sintetico: true`, URL
`demo.invalid`); las cifras de Banco Mundial, INEC y USGS son las reales de `data/processed/`. La interfaz debe mostrar
un aviso mientras `sintetico` sea verdadero.

## Pantallas y datos que consume cada una

Las etapas son las del §3. Hora de Panamá en toda la interfaz: los datos viajan en UTC (`…Z`) y la interfaz convierte.

| # | Pantalla (etapa) | Qué muestra | Datos que necesita | Origen |
|---|---|---|---|---|
| 1 | **Reporte de calidad** (1 Cargar) | Qué entró, qué se excluyó y por qué; nulos conservados; cobertura por fuente; integridad del snapshot | `ventana`, `registros_leidos`, `incluidas`, `excluidas_por_motivo`, `cobertura_por_fuente` de `calidad_noticias.json`; `filas_*` de `calidad_indicadores.json`, `calidad_inec.json`, `calidad_eventos.json`; `version`, `fecha_corte_UTC`, `sha256` de `manifest.json` | G1, archivos existentes (sin esquema nuevo) |
| 2 | **Bandeja priorizada** (2-4) | Grupos ordenados por puntaje, con componentes, rango y estado de evidencia | `Grupo`: `titulo`, `tema` (etiqueta en `TOPIC_LABELS`), `puntaje.valor/rango/componentes/version_reglas`, `estado_evidencia`, `estado_revision`, `n_noticias/n_medios/n_procedencias`, `id_caso` | G3 → `grupos.jsonl` |
| 3 | **Grupo de noticias** (2) | Miembros del grupo, medios frente a procedencias independientes, noticias recirculadas con su fecha original | `Grupo.miembros`: `titulo`, `url`, `medio`, `procedencia`, `fecha_publicacion`, `alcance_texto`, `recirculada_en` | G3 → `grupos.jsonl` |
| 4 | **Contexto oficial** (3) | Indicador o sismo vinculado con período, unidad y limitaciones; o por qué no hay vínculo | `Grupo.contexto`: `etiqueta`, `pais`, `periodo`, `valor` (puede ser nulo), `unidad`, `limitaciones`, `razon`; si no hay, `sin_contexto_motivo` | G3 → `grupos.jsonl` |
| 5 | **Ficha de evidencia** (5 Explicar) | Qué se reporta y quién; qué está respaldado; qué falta; contradicciones; acción recomendada; citas navegables | `Ficha`: `afirmaciones` (`tipo`, `atribuida_a`, `citas`), `vacios`, `contradicciones`, `accion_recomendada`, `alcance_texto`; cada `Cita` se abre con `Evidencia` (`url`, `fecha`, `campos`) | G4 → `fichas.jsonl` + `evidencias.jsonl` |
| 6 | **Paquete editorial** (6 Producir) | Brief, título, enfoque, 3 preguntas, fuentes y verificaciones, guion, copy; hechos, declaraciones, inferencias e hipótesis diferenciados | `Ficha.borrador` (`PaqueteEditorial`, incluida `leyenda`) y `Ficha.afirmaciones[].tipo`. `borrador` es nulo cuando no hay evidencia para redactar | G4 → `fichas.jsonl` |
| 7 | **Revisión humana** (7 Revisar) | Estado actual, responsable, fecha, nota e historial; cambio de estado | `RegistroRevision`: `id_caso`, `estado`, `responsable`, `fecha`, `nota`. El estado actual es el último registro | G5 → `revisiones.jsonl` |
| 8 | **Caja de consultas** | Respuesta con citas, o abstención con lo que falta, o ambas versiones de una contradicción | `Respuesta`: `estado`, `respuesta`, `citas`, `motivo_abstencion`, `faltante`, `versiones`. Sin red solo responde las precalculadas (D-01) | G4 → `consultas.jsonl` |

## Reglas que el código ya hace cumplir

Construir un registro inválido lanza `ValueError`, así que ningún carril entrega algo que otro deba desconfiar.

- **Puntaje:** `P = 30R + 25I + 20U + 15N + 10E`, componentes en 0-1. El valor y el rango se **derivan** de los
  componentes; no se aceptan de afuera. Los cinco componentes llevan justificación y la versión de reglas.
  Rangos sin solapamiento: bajo `[0,40)`, medio `[40,70)`, alto `[70,100]`. Desempate: mayor `U`, luego `id_grupo`
  (`ordenar_bandeja`).
- **Citas:** toda afirmación cita al menos una evidencia. `errores_de_citas` comprueba que el ID exista, que el campo
  exista y que el pasaje sea **literal**; es la base del verificador determinista de G4.
- **Declaraciones:** una afirmación de tipo `declaracion` exige `atribuida_a`. Las acusaciones nunca son hechos.
- **Evidencia independiente del puntaje:** una ficha con evidencia `insuficiente` no puede pasar a
  `aprobado_como_borrador`, y si la evidencia no es suficiente debe decir qué falta en `vacios`.
- **Solo titular:** si `alcance_texto` es `titular_metadatos`, el borrador lleva la leyenda
  «basado únicamente en titular/metadatos».
- **Paquete editorial:** brief ≤ 250 palabras, copy ≤ 80, exactamente 3 preguntas.
- **Procedencias:** `n_procedencias` cuenta orígenes distintos; una agencia replicada por tres medios es una sola.
- **Contexto oficial:** nunca sin período, unidad y limitaciones. Si no hay vínculo sustentado, `sin_contexto_motivo`
  explica por qué y no se fuerza uno.
- **Noticia recirculada:** `fecha_publicacion` es la original; `recirculada_en` es posterior (T03).
- **Revisión:** todo estado distinto de `nuevo` nombra un responsable (una persona).

## `fichas.jsonl` (§7)

Los campos mínimos van primero y en el orden del reto: `id_caso`, `modalidad`, `ids_fuente`, `afirmaciones`, `citas`,
`puntaje` (número), `componentes` (`R`, `I`, `U`, `N`, `E`), `estado_evidencia`, `borrador`, `estado_revision`.
`citas` repite las de las afirmaciones, sin duplicados. Después van los campos de las pantallas: `puntaje_detalle`
(`rango`, `version_reglas`, `justificaciones`), `id_grupo`, `titulo`, `tema`, `alcance_texto`, `vacios`,
`contradicciones`, `accion_recomendada`, `sintetico`.

## Decisiones que otros carriles deben conocer

- **Temas:** el contrato usa slugs (`economia`, `logistica_canal`, `turismo`, `servicios_publicos`,
  `eventos_naturales`, `regulacion`, más `sin_tema`). El clasificador de `src/ai` devuelve hoy las etiquetas del PDF
  (`"economía"`, `"logística/Canal"`…): debe mapearlas a estos slugs. Los nombres para mostrar están en `TOPIC_LABELS`.
- **IDs de evidencia:** `N-<hash>` (noticia), `WB-<país>-<indicador>-<año>`, `INEC-<serie>-<período>` y
  `USGS-<id>`. El prefijo debe coincidir con el tipo.
- **Los componentes R e I** los decide G3; este contrato solo exige que estén en 0-1 y justificados.
- **Sin vínculo forzado:** un sismo de USGS solo se enlaza a una noticia sobre ese sismo. En la demostración, el grupo
  `G-006` es una noticia de diciembre de 2025 recirculada en octubre de 2026 y se vincula al sismo de esa misma fecha
  (T03 y contexto USGS a la vez).
- **Persistencia de la revisión (G5):** este contrato define el registro; dónde se guarda lo decide G5.
