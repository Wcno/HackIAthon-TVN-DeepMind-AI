# Catálogo de datos

> Espeja la página «Catálogo de datos» del §5. Las cifras y los hashes vienen de
> `data/manifest.json` (versión `20261008-c2aa2916`, corte `2026-10-08T00:51:38Z`). Cada
> archivo procesado tiene su SHA-256 en ese manifest.

## Origen y fecha de extracción

| Fuente | URL consultada | Extracción (UTC) |
| --- | --- | --- |
| TVN | `https://www.tvn-2.com/rss/` y sitemaps mensuales `tvn_sitemap_contents_*.xml` | 2026-10-07 03:32 a 04:00 |
| GDELT DOC 2.0 | `https://api.gdeltproject.org/api/v2/doc/doc` (consultas por país, PM) | 2026-10-08 00:43 a 00:51 |
| GDELT GKG | `https://data.gdeltproject.org/gdeltv2/` (seis lotes horarios, 18:00 a 23:00 del 7 de octubre) | 2026-10-08 00:47 |
| Prensa | `https://www.prensa.com/arc/outboundfeeds/news-sitemap/?outputType=xml` | 2026-10-08 00:43 |
| Telemetro | `https://www.telemetro.com/sitemap-news.xml` | 2026-10-08 00:43 |
| Panamá América | `https://www.panamaamerica.com.pa/rss/recent/index.xml` | 2026-10-08 00:43 |
| Entidades oficiales | API WordPress de MEF, MICI, ATP, AMP, Sinaproc y ACP (`/wp-json/wp/v2/posts`) | 2026-10-07 04:35 a 04:36 |
| Banco Mundial | `https://api.worldbank.org/v2/country/PAN;CRI;COL;DOM;MEX;GTM/indicator/{id}` | 2026-10-07 04:32 |
| USGS | `https://earthquake.usgs.gov/fdsnws/event/1/query` (caja regional) | 2026-10-07 04:32 |
| INEC | catálogos y archivos de IPC y PIB trimestral | 2026-10-07 04:36 |

## Noticias (fuente A)

| Fuente | Incluidas | Licencia y condiciones | Notas |
| --- | --- | --- | --- |
| TVN | 2.728 | Sin condiciones de reutilización publicadas. Solo metadatos; no se redistribuye el cuerpo. | Fecha de publicación del feed, de la página (reediciones) o del `lastmod`. |
| Telemetro | 187 | El sitio no publica condiciones de reutilización de sus feeds. Solo metadatos y descripción breve. | Sitemap de noticias. |
| Prensa | 100 | Igual que Telemetro. | Sitemap de noticias. |
| Panamá América | 24 | Igual que Telemetro. | RSS. |
| Día a Día | 14 | Igual que Telemetro. Metadatos indexados por GDELT, con atribución; GDELT no transfiere derechos. | Vía GDELT. |
| RPC TV | 7 | Igual que Día a Día. | Vía GDELT. |
| ACP (Pancanal) | 13 | Los términos del sitio restringen la copia; solo metadatos y extracto de la API. | Entidad oficial. |
| Sinaproc | 32 | Comunicado de entidad pública, sin condiciones declaradas. | Entidad oficial. |
| MEF | 13 | Igual que Sinaproc. | Entidad oficial. |
| MICI | 31 | Igual que Sinaproc. | Entidad oficial. |
| ATP | 8 | Igual que Sinaproc. | Entidad oficial. |
| AMP | 19 | Igual que Sinaproc. | Entidad oficial. |
| **Total** | **3.176** | | |

GDELT aporta fechas de detección (`fecha_deteccion`), nunca de publicación. El manifest
también nombra La Estrella, Mi Diario y Crítica, pero no tienen noticias incluidas en este corte.

Ventana: 30.823 registros leídos, 30.462 noticias únicas, 3.176 incluidas y 27.286 excluidas
por fuera de la ventana (`data/processed/calidad_noticias.json`).

**Conciliación pendiente:** `evidencias.jsonl` tiene 2.941 noticias. Las 235 restantes de las
3.176 incluidas no aparecen como evidencia, y el repositorio no documenta por qué.

## Banco Mundial (fuente B)

Seis países (PAN, CRI, COL, DOM, MEX, GTM), seis indicadores y años 2010 a 2024.
Licencia CC BY 4.0, con atribución. Se obtuvieron 540 observaciones. La unidad se deriva del
indicador porque el campo viene vacío. Los nulos se conservan, nunca se rellenan con cero.

## USGS (fuente C)

Caja regional (lat 5 a 12, lon -86 a -76), magnitud 3 o más, desde 2025-10-02 (D-02 del equipo).
Dominio público (EE. UU.). Se obtuvieron 88 eventos. La caja no coincide con el territorio
de Panamá: los sismos solo se usan como hechos sísmicos.

## INEC (fuente adicional)

Índice de precios y PIB trimestral desde 2022, en formato largo. Licencia CC BY 4.0.
Se obtuvieron 144 observaciones. Los períodos duplicados en origen se excluyen.

## SBP (fuente D)

No usada. La modalidad bancaria quedó fuera (ver DP-01 en `02-plan-y-decisiones.md`).

## Integridad del snapshot

`data/manifest.json` guarda la versión, la fecha de corte, las consultas exactas, las
cantidades, las licencias y el SHA-256 de cada archivo procesado. Las pruebas comparan los
bytes contra esos hashes (`tests/test_backend_quality.py`).
