# hackiaton-whoamisfc

Este repositorio es para la hackathon.

## Run the G5 backend

```powershell
uv sync --locked --link-mode copy
uv run --locked uvicorn whoami.backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000/inbox. The initial workflow uses synthetic news and
precomputed queries, without a Gemini key. Human decisions persist in SQLite
outside the checkout. See [the backend contract](docs/backend.md) for G4/G6
integration, runtime settings, available screens and validation.

```powershell
uv run --locked pytest -q
```

Stop the server and export the current human review cycle with
`uv run --locked whoami export-backend --output outputs`.
The test suite includes a real HTTP server restart and G2 export round-trip.

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

### Configuración de GitHub y despliegue

- Usar `prod` como rama predeterminada.
- Proteger `prod`: exigir pull request y una aprobación de otro integrante; aplicar la regla también a administradores e impedir force pushes y la eliminación de la rama.
- Invalidar aprobaciones cuando se suban cambios nuevos al pull request.
- Exigir los checks de `G5 validation`: pruebas y build en Windows y Linux. La protección de rama debe configurarse en GitHub.
- Configurar el proveedor de despliegue para publicar desde `prod`; actualmente no hay un despliegue configurado.

Estas son las reglas acordadas. La protección, la rama predeterminada y el despliegue deben verificarse en sus respectivas plataformas.
