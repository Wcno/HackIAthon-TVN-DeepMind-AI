# Cómo contribuir

La rama de integración y producción es `prod`.
Cada cambio se desarrolla en una rama corta y se integra mediante un pull request hacia `prod`, con los checks configurados en verde.
No se requiere una aprobación para fusionar.
No usamos una rama `dev`.

## Flujo

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

También se usan ramas `fix/nombre-del-arreglo` para correcciones.
No se hacen pushes directos a `prod`.

## Configuración de GitHub y despliegue

- Usar `prod` como rama predeterminada.
- Proteger `prod`: exigir pull request y los checks configurados, sin aprobaciones obligatorias.
  Aplicar la regla también a administradores e impedir force pushes y la eliminación de la rama.
- Exigir los checks de `G5 validation`: pruebas y build en Windows y Linux.
- Configurar el proveedor de despliegue para publicar desde `prod`; actualmente no hay un despliegue configurado.

Estas son las reglas acordadas.
La protección, la rama predeterminada y el despliegue deben verificarse en sus respectivas plataformas.
