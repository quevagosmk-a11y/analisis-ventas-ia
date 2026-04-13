# Despliegue en Railway desde Windows

Este flujo deja el sistema publicado por URL sin depender del computador local encendido y sin administrar un servidor Linux manualmente.

## Qué quedó preparado

- [railway.json](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/railway.json)
- [Dockerfile](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/Dockerfile)
- [docker/entrypoint.sh](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/docker/entrypoint.sh)
- [.env.railway.example](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/.env.railway.example)
- [scripts/export_beta_dump.ps1](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/scripts/export_beta_dump.ps1)

La aplicación quedó lista para:

- desplegarse desde GitHub usando el `Dockerfile`
- leer MySQL desde `DATABASE_URL`, `MYSQL_URL` o variables `MYSQLHOST/MYSQLPORT/...`
- responder `200 OK` en `GET /healthz` para el healthcheck de Railway
- usar volumen de Railway para respaldos si se adjunta uno

## Requisitos

- cuenta en GitHub
- cuenta en Railway
- repositorio subido a GitHub
- base beta local accesible para exportar

Fuentes oficiales consultadas:

- Railway Flask: https://docs.railway.com/guides/flask
- Railway Dockerfiles: https://docs.railway.com/builds/dockerfiles
- Railway variables: https://docs.railway.com/variables/reference
- Railway MySQL: https://docs.railway.com/databases/mysql
- Railway config as code: https://docs.railway.com/config-as-code/reference

## 1. Subir el proyecto a GitHub

Si el proyecto aún no está en GitHub, súbelo primero. Railway desplegará directamente desde ese repositorio.

## 2. Crear el proyecto en Railway

1. Entrar a Railway.
2. Crear un proyecto nuevo.
3. Elegir `Deploy from GitHub repo`.
4. Seleccionar este repositorio.

Railway detectará el [Dockerfile](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/Dockerfile) automáticamente y aplicará [railway.json](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/railway.json).

## 3. Agregar MySQL en Railway

1. En el mismo proyecto, pulsar `New`.
2. Agregar un servicio `MySQL`.

Según la documentación oficial de Railway, el servicio MySQL expone estas variables para otras aplicaciones del proyecto:

- `MYSQLHOST`
- `MYSQLPORT`
- `MYSQLUSER`
- `MYSQLPASSWORD`
- `MYSQLDATABASE`
- `MYSQL_URL`

## 4. Configurar variables de la app web

En el servicio web, crea estas variables:

- `DATABASE_URL`
- `APP_SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_VENDOR_PASSWORD`
- `SESSION_COOKIE_SECURE`
- `SESSION_COOKIE_SAMESITE`
- `FLASK_DEBUG`
- `ALLOW_DEV_LOGIN`

Valores recomendados:

- `DATABASE_URL`: crearla como referencia al `MYSQL_URL` del servicio MySQL
- `APP_SECRET_KEY`: una clave larga y única
- `DEFAULT_ADMIN_PASSWORD`: clave inicial del administrador
- `DEFAULT_VENDOR_PASSWORD`: clave inicial del vendedor
- `SESSION_COOKIE_SECURE=1`
- `SESSION_COOKIE_SAMESITE=Lax`
- `FLASK_DEBUG=0`
- `ALLOW_DEV_LOGIN=0`

Si quieres conservar respaldos dentro de Railway:

1. Agrega un volumen al servicio web.
2. Usa `/data` como punto de montaje.

La aplicación detectará automáticamente `RAILWAY_VOLUME_MOUNT_PATH` y guardará los respaldos en `/data/backups`.

## 5. Publicar la URL

1. Abrir el servicio web.
2. Ir a `Settings` -> `Networking`.
3. Pulsar `Generate Domain`.

La URL quedará con un dominio `*.up.railway.app`.

## 6. Exportar la base beta desde Windows

Desde PowerShell, en la raíz del proyecto:

```powershell
.\scripts\export_beta_dump.ps1
```

Eso genera:

```text
deploy\railway\beta_dump.sql
```

Si `mysqldump` no existe en tu Windows, instala `MySQL Client`, `MariaDB Client` o usa la consola incluida por XAMPP.

## 7. Importar la base beta en Railway

La forma más práctica desde Windows es usar MySQL Workbench, DBeaver o cualquier cliente MySQL gráfico.

1. Abrir el servicio MySQL en Railway.
2. Ir a la sección de conexión externa.
3. Copiar host, puerto, usuario, contraseña y base.
4. Conectarte desde MySQL Workbench o DBeaver.
5. Importar el archivo `deploy\railway\beta_dump.sql`.

También puedes usar `mysql.exe` en PowerShell si ya lo tienes instalado:

```powershell
mysql -h HOST_PUBLICO -P PUERTO -u USUARIO -p BASE < .\deploy\railway\beta_dump.sql
```

## 8. Verificación mínima

Una vez desplegado:

1. Abrir la URL pública.
2. Iniciar sesión con el usuario administrador.
3. Confirmar módulos principales:
   - dashboard
   - registrar venta
   - productos
   - reportes
   - auditoría
4. Probar el endpoint de salud:

```text
https://TU-DOMINIO.up.railway.app/healthz
```

Debe responder `200` con JSON.

## Observaciones prácticas

- Cada nuevo despliegue vuelve a ejecutar `bootstrap`; eso es seguro porque el backend ya trabaja con creación idempotente de tablas y migraciones.
- Si cambias credenciales base después del primer arranque, no sobrescribe usuarios existentes; esas variables aplican al bootstrap inicial o a restauraciones controladas.
- Railway no exige que administres Linux manualmente, pero el servicio corre en infraestructura Linux administrada por la plataforma.
