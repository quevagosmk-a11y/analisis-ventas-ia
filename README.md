# Analisis de Ventas IA

Aplicacion Flask para gestionar inventario, ventas y recomendaciones inteligentes.

## Configuracion Rapida (Windows)

1. Abre PowerShell en el directorio del proyecto y ejecuta:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
   ```
   El script crea el entorno virtual `.venv`, instala dependencias y agenda la limpieza horaria de sesiones.
2. Copia `.env.example` a `.env` y completa tus credenciales MySQL, `APP_SECRET_KEY`, etc.
3. Para levantar el backend usa:
   ```bat
   scripts\run_app.bat
   ```
   (puedes crear un acceso directo a este archivo en el escritorio).
4. Si es la primera vez que usas la base de datos, inicializa las tablas básicas y el usuario admin corriendo:
   ```powershell
   .\.venv\Scripts\python.exe src\main.py bootstrap
   ```

### Opción manual (Linux/WSL/usuarios avanzados)

```bash
python -m venv .venv
.venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

## Usuarios, perfiles y roles (estado actual)

- `admin`: gestiona usuarios, sesiones, productos, reportes, estadisticas y respaldos.
- `gerente`: opera ventas, productos, reportes, estadisticas, auditoria y respaldos.
- `vendedor`: registra ventas, consulta inventario, dashboard e insights IA.

Credenciales semilla (bootstrap):

- `admin / valor de DEFAULT_ADMIN_PASSWORD`
- `vendedor / valor de DEFAULT_VENDOR_PASSWORD`

Preparar o restaurar ambos usuarios base en Windows:

```bat
scripts\setup_users.bat --admin-pass="<clave-admin>" --seller-pass="<clave-vendedor>"
```

Sincronizar catálogo de tienda de barrio (precios COP + stock realista):

```bat
.\.venv\Scripts\python.exe src\main.py sync_barrio_catalog
```

> Recomendado para entrega: cambia las claves por defecto en `.env` (`DEFAULT_ADMIN_PASSWORD`, `DEFAULT_VENDOR_PASSWORD`) y define `APP_SECRET_KEY` fuerte.

> Nota: actualmente el sistema incluye `admin`, `gerente` y `vendedor`.  
> Si tu matriz academica exige perfiles adicionales (`jefe_bodega`, `cajero`), se recomienda extender permisos por modulo en backend y frontend.

## Despliegue Docker en Windows (recomendado para entrega)

Este es el camino mas simple para pasar el proyecto a otro computador con Windows.

1. Instala Docker Desktop (incluye Docker Compose).
2. Copia esta carpeta al nuevo computador (USB, Drive o ZIP).
3. En la carpeta del proyecto:
   - copia `.env.docker.example` como `.env.docker`.
   - edita `APP_SECRET_KEY` y `DB_PASSWORD`.
4. Ejecuta:
   ```bat
   scripts\run_docker.bat
   ```
5. Abre `http://localhost:5000`.

Apagado:

```bat
scripts\stop_docker.bat
```

Reset completo de datos Docker (opcional):

```bat
scripts\reset_docker_data.bat
```

Incluido en Docker:

- `docker-compose.yml` (servicios `app` + `mysql`).
- `Dockerfile` (imagen del backend).
- `docker/entrypoint.sh` (espera MySQL, ejecuta `bootstrap`, inicia app).

## Publicar por URL en un VPS con Docker

Si necesitas compartir el sistema por URL sin dejar tu PC prendido, el repositorio ya quedó preparado para un VPS Linux con Docker.

Archivos principales:

- `docker-compose.vps.yml`
- `.env.vps.example`
- `scripts/vps_up.sh`
- `scripts/vps_import_sql.sh`
- `scripts/export_beta_dump.sh`
- `docs/DEPLOY_VPS.md`

Flujo corto:

1. Genera un dump beta:
   ```bash
   bash scripts/export_beta_dump.sh
   ```
2. Sube el proyecto al VPS.
3. En el VPS:
   ```bash
   cp .env.vps.example .env.vps
   bash scripts/vps_up.sh
   ```
4. Abre:
   ```text
   http://IP_DEL_VPS/
   ```

Guía completa:

- `docs/DEPLOY_VPS.md`

## Publicar por URL en Railway desde Windows

Si no quieres administrar un servidor Linux, el repositorio también quedó preparado para Railway.

Archivos principales:

- `railway.json`
- `.env.railway.example`
- `scripts/export_beta_dump.ps1`
- `docs/DEPLOY_RAILWAY.md`

Qué resuelve esta ruta:

- URL pública sin dejar tu PC encendido
- despliegue del backend desde GitHub usando el `Dockerfile`
- base MySQL separada como servicio gestionado dentro de Railway
- healthcheck estable en `GET /healthz`
- compatibilidad con `DATABASE_URL`, `MYSQL_URL` y variables `MYSQLHOST/MYSQLPORT/...`

Flujo corto:

1. Subir este proyecto a GitHub.
2. Crear proyecto en Railway desde ese repo.
3. Agregar un servicio `MySQL`.
4. En la app web, crear `DATABASE_URL` como referencia a `MYSQL_URL` del servicio MySQL.
5. Definir `APP_SECRET_KEY`, `DEFAULT_ADMIN_PASSWORD` y `DEFAULT_VENDOR_PASSWORD`.
6. Generar dominio público en `Networking`.
7. Exportar la base beta desde Windows:
   ```powershell
   .\scripts\export_beta_dump.ps1
   ```
8. Importar `deploy\railway\beta_dump.sql` a MySQL desde Workbench/DBeaver.

Guía completa:

- `docs/DEPLOY_RAILWAY.md`

## Limpieza de sesiones

El backend mantiene la tabla `sesiones_activas` sincronizada cada vez que se consulta o almacena una sesion. Ademas se expusieron dos mecanismos manuales:

- **CLI**: `python src/main.py cleanup_sessions` revoca las sesiones expiradas y muestra cuantas filas fueron afectadas. Ideal para usar con Programador de tareas (Windows) o `cron` (WSL/Linux).
- **Endpoint admin**: `POST /api/sesiones/limpiar` (requiere sesion admin) invoca la misma limpieza y devuelve `{ success: true, revoked: N }`.

Ejemplo de tarea programada en Windows (PowerShell):
```powershell
schtasks /Create /SC HOURLY /TN "CleanupSesiones" /TR "python C:\ruta\al\repo\src\main.py cleanup_sessions"
```

## Flujo de ventas transaccional

- Todas las ventas se envuelven en `BEGIN/COMMIT` y cualquier error genera `ROLLBACK`.
- Se registran auditorias cuando se fuerza un cambio de precio.
- El servicio devuelve `500` pero deja stock, ventas y auditorias intactos si se produce un fallo intermedio.

## Validacion de precios y stock

- Se aceptan entradas con formato local (`$ 1.234,50`, `1.000`, etc.) y se rechazan combinaciones ambiguas.
- Estos chequeos estan centralizados en `src/utils/numeric.py`.

## Desarrollo

- Ejecutar pruebas: `PYTHONPATH="$(pwd)/analisis-ventas-ia" pytest`.
- Mantener el entorno sincronizado con la base MySQL antes de correr los tests de integracion.
- Para checks de calidad instala tambien las dependencias de desarrollo: `pip install -r requirements-dev.txt`.

## Migraciones de esquema

- El proyecto ahora registra migraciones en la tabla `schema_migrations`.
- Arranque normal: `python src/main.py` intenta aplicar migraciones pendientes al iniciar.
- Ejecucion manual: `python src/main.py migrate`.
- Bootstrap completo: `python src/main.py bootstrap`.
- Verifica el resultado revisando la salida `[schema]` en consola.

## Calidad de codigo (entrega presentable)

Este repositorio ahora incluye convenciones y chequeos basicos para mantener codigo limpio:

- `.editorconfig` (indentacion y saltos de linea consistentes).
- `pyproject.toml` (configuracion de `black`, `ruff` y `pytest`).
- `.gitignore` para evitar subir artefactos temporales.

Validacion rapida en Windows:

```bat
scripts\check_quality.bat
```

Validacion rapida en Linux/WSL:

```bash
./scripts/check_quality.sh
```

## Respaldo y modo offline

- Respaldos automaticos configurables mediante las variables `APP_AUTO_BACKUP_INTERVAL` y la carpeta `backups/`.
- Respaldo manual disponible con `python src/main.py backup` para generar instantaneas de productos y ventas.
- El backend usa automaticamente el ultimo snapshot cuando no hay conexion a MySQL, operando en modo solo lectura.
- El frontend muestra una alerta de modo resiliente y mantiene la navegacion con datos locales mientras vuelve la conectividad.
- Los administradores pueden generar un respaldo manual desde el panel *Mi perfil* con el boton `Generar respaldo`.

### Restaurar un respaldo

1. Inicia sesion como admin.
2. Abre el modulo **Respaldos**.
3. Pulsa `Actualizar lista` si no ves el snapshot.
4. Descarga el JSON/PDF si quieres revisarlo.
5. Usa `Restaurar` sobre el snapshot deseado.

La restauracion reemplaza productos, ventas, detalle e inventario del sistema con el contenido del snapshot seleccionado. El evento queda registrado en auditoria como `respaldo_restaurado`.

## Inventario masivo

- En **Productos** ahora puedes `Exportar CSV`, `Exportar Excel` e `Importar archivo`.
- La importacion acepta `.csv` y `.xlsx`.
- Columnas minimas requeridas: `nombre`, `precio`, `stock`, `min_stock`.
- Columnas opcionales: `id`, `categoria`, `iva_percent`, `activo`, `imagen_data_url`.
- Si el archivo trae `id` existente se actualiza ese producto; si no, se intenta empatar por nombre. Si no existe coincidencia, se crea un producto nuevo.
- Las importaciones y exportaciones quedan registradas en auditoria.

## Entrenamiento del modelo IA

- El script `scripts/train_demand_model.py` entrena un `RandomForestRegressor` con las ventas historicas.
- Uso sugerido: `python scripts/train_demand_model.py --window 30 --horizon 14`. Genera `models/demand_model.joblib`.
- Si MySQL no esta disponible, usa `--csv data/demo_sales_evaluacion.csv` (tambien intenta automaticamente `data/sales_data.csv`, `data/demo_sales_evaluacion.csv` y `data/sample_sales.csv`).
- El backend carga el modelo desde `models/demand_model.joblib` (cambiar ruta con `AI_DEMAND_MODEL_PATH`).
- El entrenamiento ahora reporta metricas de entrenamiento, validacion temporal y baseline estadistico para comprobar si el modelo realmente mejora.
- Cuando no exista modelo entrenado, la IA usa automaticamente una prediccion heuristica por promedio diario (no deja el sistema sin recomendaciones).
- Endpoint nuevo para tablero admin: `GET /api/ia/pronostico-demanda` (acepta `from`, `to`, `horizon`, `window`, `limit`) y devuelve riesgo de quiebre, cobertura y compra sugerida por producto.
- El frontend muestra este pronostico dentro de **Estadisticas**, incluyendo calidad del modelo (`MAPE`) y confianza estimada.

## Escenario demo IA para evaluadores (datos ficticios)

Para dejar el proyecto listo con datos de prueba y modelo entrenado en una sola corrida:

```powershell
.\scripts\setup_demo_ai.bat
```

Ese comando ejecuta:

1. Generacion de un CSV ficticio realista (`data/demo_sales_evaluacion.csv`) con estacionalidad, promociones y tendencia.
2. Carga completa en MySQL (productos + ventas) reemplazando datos anteriores.
3. Entrenamiento del modelo de demanda y guardado en `models/demand_model.joblib`.
4. Verificacion final de predicciones IA y sugerencias de reposicion.

Opciones utiles:

- `.\scripts\setup_demo_ai.bat --days=540` (mas historial).
- `.\scripts\setup_demo_ai.bat --seed=2027` (otro escenario reproducible).
- `.\scripts\setup_demo_ai.bat --no-replace` (no borrar datos previos).
- `.\scripts\setup_demo_ai.bat --admin-pass="<clave-admin>"` (define la clave final del admin).
- `.\scripts\setup_demo_ai.bat --help` (ver todas las opciones).

## Seguridad Operativa

- Endpoints de IA y productos ahora requieren sesion activa.
- Reportes y estadisticas estan restringidos a rol `admin`.
- Las contraseñas se almacenan con `PBKDF2-SHA256` y el sistema migra hashes antiguos al iniciar sesion.
- El login aplica bloqueo temporal local despues de multiples intentos fallidos consecutivos.
- Sesiones, logins, exports, cambios de IVA y respaldos dejan trazabilidad en auditoria.

## Despliegue y mantenimiento

1. Configura la base de datos y variables `.env`.
2. Verifica la tarea programada: `schtasks /Query /TN "AnalisisVentas_Cleanup"`.
3. Para limpiar sesiones manualmente:
   ```powershell
   .\.venv\Scripts\python.exe src\main.py cleanup_sessions
   ```
4. Si no puedes iniciar sesión (credenciales olvidadas), puedes recuperar acceso:
   ```powershell
   .\.venv\Scripts\python.exe src\main.py unlock_admin
   ```
   También puedes definir una nueva clave:
   ```powershell
   .\.venv\Scripts\python.exe src\main.py unlock_admin "NuevaClaveSegura1!"
   ```
5. Para dejar listos los perfiles operativos base (`admin` y `vendedor`) en una sola ejecución:
   ```powershell
   .\.venv\Scripts\python.exe src\main.py setup_users --admin-pass="<clave-admin>" --seller-pass="<clave-vendedor>"
   ```
6. Revisa `logs/` y la consola para mensajes `[session]` o `[ventas]`.

## Smoke test del frontend

Existe un smoke test real de navegador en `scripts/smoke_frontend.py` para validar login, dashboard, productos, auditoria y respaldos.

Preparacion:

```bash
pip install playwright
playwright install chromium
```

Ejecucion:

```bash
python scripts/smoke_frontend.py --base-url http://127.0.0.1:5000/
```

Tambien puedes usar:

```bash
npm run smoke:frontend
```

El script deja evidencia en `artifacts/smoke/`.

## Licencia

MIT.
