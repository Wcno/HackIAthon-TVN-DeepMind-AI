# Riesgos y ética

> Espeja la página «Riesgos y ética» del §5: privacidad, derechos, sesgos, ataques al
> agente, controles y escenarios fuera de alcance (§8).

## Controles y dónde están

| Control | Exigencia | Implementación |
| --- | --- | --- |
| Control humano | Estados de revisión; aprobar no es publicar | `REVIEW_STATES` y `ReviewState` en `contracts.py`; transiciones validadas en `schemas.py` |
| Anti-alucinación | No inventar cifras, personas ni fuentes | Esquema JSON estricto y verificador determinista de citas (`generation/verifier.py`) |
| Abstención | Si falta evidencia, abstenerse y decir qué falta | Compuerta de coseno antes de generar; el modelo solo propone |
| Anti-inyección | El texto de una fuente es dato, no instrucción | Evidencia en turno `user` dentro de etiquetas neutralizadas; reglas en `system`; canario de fuga |
| Privacidad | No guardar datos personales innecesarios | Solo metadatos públicos: titular, URL, medio y fecha |
| Atribución | Acusaciones como declaraciones | Tipo `declaracion` obligatorio en las afirmaciones |
| Derechos | Condiciones registradas por fuente; sin redistribuir contenido | `data/manifest.json` (licencias) y `data/processed/fuentes.json` |
| Credenciales | Fuera del código y de Notion | `.env` en `.gitignore`; `.env.example` sin secretos; la clave nunca va en logs ni fichas |

## Riesgos abiertos

| Riesgo | Impacto | Mitigación | Estado |
| --- | --- | --- | --- |
| No llega la licencia Business de Notion | **Descalificación**: §5 condiciona la admisión al espacio | Confirmar la licencia; si no llega, crear un espacio gratuito antes del cierre. `docs/notion/` ya tiene las ocho páginas listas. | Abierto |
| Límites del tier gratuito de Gemini no publicados | Quedarse sin cuota en pleno evento | Revisar el panel de AI Studio; cachear respuestas; embeddings locales | Abierto |
| Google puede usar los datos del tier gratuito para mejorar sus productos | Privacidad | Se envían titulares, descripciones breves y metadatos de noticias públicas; sin datos personales de usuarios; documentado aquí | Aceptado |
| Gemma devuelve JSON inválido en respuestas largas | Fallos de generación | Generación con flash-lite; Gemma solo para tareas cortas; JSON inválido nunca entra en caché | Mitigado |
| Sin red no hay generación en vivo | **Falla T10** | Caché de respuestas y consultas precalculadas (35 en `consultas.jsonl`); ensayo con el wifi apagado | Pendiente de ensayo |
| Citas falsas: un ID real con un pasaje que no lo respalda | Pérdida de credibilidad | Verificador determinista: ID existente, pasaje literal y cifras normalizadas | Mitigado con pruebas |
| Derechos del contenido de TVN | Legal | Solo metadatos; los términos de TVN prohíben copiar contenido | Mitigado |
| Etiquetas y umbrales ajustados sobre el mismo conjunto de desarrollo | Métricas optimistas | Declarar que son provisionales; revisión humana antes de citar cifras | Abierto |

## Sesgos y límites declarados

- **Cobertura sesgada por fuente.** Pocos medios y varias fuentes oficiales. El corpus no
  representa todo el espacio informativo de Panamá.
- **Solo titular y metadatos de TVN** en la mayoría de los casos. No se simula la lectura
  del artículo completo.
- **La caja del USGS no es Panamá.** Sus eventos son hechos sísmicos, no evidencia de
  daños, inundaciones ni pérdidas.
- **Las cifras del Banco Mundial son series anuales históricas.** Nunca se presentan como
  cifras de hoy.
- **El P@5 del ranking es exploratorio:** no hay una persona especialista que sirva de
  referencia.
- **Nombres de personas en las noticias.** Las fichas atribuyen lo dicho a quien lo dijo,
  sin convertir acusaciones en hechos.

## Fuera de alcance (§2)

Rating, audiencia o conversión publicitaria · detección definitiva de noticias falsas ·
culpabilidad, fraude, solvencia o riesgo de crédito individual · datos personales de
clientes · perfiles de personas · contenido detrás de un muro de pago · producción
audiovisual automática · clonación de voz · integración con emisión o sistemas transaccionales.

> Una alerta es una invitación a investigar. Ni el tono, ni el volumen, ni la repetición de
> una noticia equivalen a un hecho comprobado.
