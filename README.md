# hackiaton-whoamisfc

Este repositorio es para la hackathon.

## Flujo de trabajo del equipo

La rama de integración y producción es `prod`. Cada cambio se desarrolla en una rama corta y se revisa una sola vez mediante un pull request hacia `prod`. No usamos una rama `dev` en este flujo.

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
4. Un compañero revisa el pull request. Los ajustes se suben a la misma rama.
5. Con una aprobación y los checks configurados en verde, hacer squash merge y eliminar la rama del cambio.
6. Desplegar la versión integrada en `prod` usando el proveedor que acuerde el equipo.

También se usan ramas `fix/nombre-del-arreglo` para correcciones. No se hacen pushes directos a `prod`.

### Clasificación de titulares

La primera capacidad de IA vive en `src/ai/classifier.py`. `classify_with_gemini`
usa la salida JSON estricta de Gemini para asignar un tema y una confianza validada;
el texto de la fuente se delimita como contenido no confiable para evitar inyección
de instrucciones. `keyword_baseline` es un baseline transparente para comparar la
clasificación semántica. Los casos sintéticos de desarrollo están en
`data/classification_samples.jsonl` y las pruebas no requieren red ni una API key:

```bash
python -m pytest -q
```

### Configuración de GitHub y despliegue

- Usar `prod` como rama predeterminada.
- Proteger `prod`: exigir pull request y una aprobación de otro integrante; aplicar la regla también a administradores e impedir force pushes y la eliminación de la rama.
- Invalidar aprobaciones cuando se suban cambios nuevos al pull request.
- Exigir los checks de CI cuando existan; actualmente el repositorio no tiene CI.
- Configurar el proveedor de despliegue para publicar desde `prod`; actualmente no hay un despliegue configurado.

Estas son las reglas acordadas. La protección, la rama predeterminada y el despliegue deben verificarse en sus respectivas plataformas.
