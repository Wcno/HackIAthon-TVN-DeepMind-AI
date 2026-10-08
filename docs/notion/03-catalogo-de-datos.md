# Catálogo de datos

> Espeja la página «Catálogo de datos» del §5. Las cifras vienen de
> `data/manifest.json` (versión `20261008-c2aa2916`, corte `2026-10-08T00:51:38Z`).
> El hash de cada archivo está en ese manifest.

## Noticias (fuente A)

| Fuente | Cómo se obtiene | Campos usados | Licencia y condiciones | Notas |
| --- | --- | --- | --- | --- |
| TVN | RSS `https://www.tvn-2.com/rss/` y sitemaps mensuales | titular, URL, `pubDate`, sección | Sin condiciones de reutilización publicadas. Solo metadatos; no se redistribuye el cuerpo. | Fecha de publicación del feed, de la página (reediciones) o del `lastmod`. |
| GDELT DOC 2.0 | API `doc` con consultas por país y ventana | URL, título, `seendate` | Metadatos indexados, con atribución. GDELT no transfiere derechos. | `seendate` es fecha de detección, nunca de publicación. |
| GDELT GKG | Seis lotes horarios del 7 de octubre (flujo multilingüe) | URL, título de página | Igual que GDELT DOC | Muestra parcial, no cobertura continua. |
| Prensa, Telemetro, Panamá América | Sitemap de noticias y RSS | igual que TVN | Sin condiciones declaradas | Metadatos y extracto. |
| Entidades oficiales (MEF, MICI, ATP, AMP, Sinaproc, ACP) | API WordPress | titular, URL, fecha, categoría | Comunicados de una entidad pública sin condiciones declaradas. Los términos de la ACP restringen la copia. | Fuentes primarias para el componente E. |

Cobertura de la ventana de 30 días: 30.823 registros leídos, 30.462 noticias únicas, 3.176
incluidas y 27.286 excluidas por fuera de la ventana (`data/processed/calidad_noticias.json`).
TVN aporta 2.728 de las incluidas.

## Banco Mundial (fuente B)

Seis países (PAN, CRI, COL, DOM, MEX, GTM), seis indicadores y años 2010-2024.
Licencia CC BY 4.0, con atribución. La unidad se deriva del indicador porque el campo viene
vacío. Los nulos se conservan, nunca se rellenan con cero. Se obtuvieron 540 observaciones.

## USGS (fuente C)

Caja regional (lat 5 a 12, lon -86 a -76), magnitud 3 o más, desde 2025-10-02 (D-02).
Dominio público (EE. UU.). Se obtuvieron 88 eventos. La caja no coincide con el territorio
de Panamá: los sismos solo se usan como hechos sísmicos.

## INEC (fuente adicional)

Índice de precios y PIB trimestral desde 2022, en formato largo. Licencia CC BY 4.0.
Se obtuvieron 144 observaciones. Los períodos duplicados en origen se excluyen.

## SBP (fuente D)

No usada. La modalidad bancaria quedó fuera (ver D-01 en `02-plan-y-decisiones.md`).

## Integridad del snapshot

`data/manifest.json` guarda la versión, la fecha de corte, las consultas exactas, las
cantidades, las licencias y el SHA-256 de cada archivo procesado. Las pruebas comparan los
bytes contra esos hashes (`tests/test_backend_quality.py`).
