# Inicio del reto

> Espeja la página «Inicio del reto» exigida por el §5. Mantener actualizada durante la
> ejecución, no al final.

## Equipo

| Rol | Persona | Carril |
| --- | --- | --- |
| Datos y fuentes | _por asignar_ | `src/whoami/ingest/`, `data/` |
| Pipeline y puntaje | _por asignar_ | `src/whoami/pipeline/`, `src/whoami/evaluation/` |
| Generación, backend y revisión | _por asignar_ | `src/whoami/generation/`, `src/whoami/backend/` |

Frontera entre carriles: `src/whoami/contracts.py` y `src/whoami/schemas.py`. Se modifican
de común acuerdo.

## Modalidad

**Editorial TVN.** Razones: el §1 la recomienda; la modalidad bancaria exige una cuarta
fuente (SBP, en PDF) que no está verificada; y los datos ya cubren los casos CU-01 a CU-04.

## Problema y usuario

Un equipo editorial revisa fuentes dispersas, elimina duplicados y prepara piezas con
rapidez. Que una noticia circule no significa que esté confirmada: varios medios pueden
repetir una misma agencia.

**Usuario:** editor o periodista de TVN Media.
**Resultado útil:** una bandeja de temas priorizados, una ficha con citas verificadas,
preguntas pendientes y borradores (brief de 250 palabras como máximo, guion de 45-60 s y
copy de 80 palabras como máximo).

## Alcance

**Incluye:** el flujo de punta a punta sobre un snapshot congelado: cargar, organizar,
contextualizar, priorizar, explicar, producir y revisar.

**No incluye (§2):** medición de audiencia o rating, detección definitiva de noticias
falsas, datos personales, producción audiovisual automática, integración con emisión.

## Criterios de éxito

Una persona de editorial puede pasar de fuentes dispersas a un tema investigable, con
evidencia y un borrador responsable. Metas (§9.1), con su estado actual en
[06-pruebas-y-metricas.md](06-pruebas-y-metricas.md):

- Cobertura de citas del 100 % de las afirmaciones factuales.
- Validez de sustento de al menos el 90 % sobre al menos 30 afirmaciones revisadas por humanos.
- Abstención correcta de al menos el 80 % de las consultas sin respuesta.
- Mediana de respuesta de 15 s o menos.
- Demo completa sin internet (T10).

## Accesos

| Recurso | Estado |
| --- | --- |
| Repositorio GitHub | `Wcno/hackiaton-whoamisfc`. Falta dar acceso al jurado. |
| Espacio de Notion | **Pendiente.** Confirmar la licencia Business antes de cualquier otra tarea. |
| Demo | Local con FastAPI (`whoami.backend.app`). Comando en el README. |
| Despliegue | **Pendiente.** Se hará al final, en una capa gratuita. |
