# Despliegue VPS con Docker

Este proyecto quedó preparado para publicarse en un VPS Linux con Docker y compartirlo por URL sin depender del computador local.

## Archivos preparados

- [docker-compose.vps.yml](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/docker-compose.vps.yml)
- [.env.vps.example](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/.env.vps.example)
- [vps_up.sh](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/scripts/vps_up.sh)
- [vps_down.sh](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/scripts/vps_down.sh)
- [vps_logs.sh](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/scripts/vps_logs.sh)
- [vps_import_sql.sh](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/scripts/vps_import_sql.sh)
- [export_beta_dump.sh](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/scripts/export_beta_dump.sh)

## Qué hace esta configuración

- Publica la aplicación web en el puerto `80` del VPS.
- Mantiene MySQL privado dentro del stack Docker.
- Conserva respaldos en la carpeta `backups/`.
- Permite cargar tu base beta mediante un `dump` SQL.

La URL mínima queda así:

```text
http://IP_DEL_VPS/
```

## Flujo recomendado

### 1. Preparar el dump beta en tu equipo actual

Desde la raíz del proyecto:

```bash
bash scripts/export_beta_dump.sh
```

Eso intentará crear:

```text
deploy/vps/mysql-init/01-beta.sql
```

Si `mysqldump` no está instalado, exporta tu base manualmente y guarda el archivo con ese mismo nombre.

### 2. Subir el proyecto al VPS

Opciones comunes:

- subirlo a GitHub y clonar en el VPS
- copiarlo por `scp`
- comprimirlo y enviarlo por SFTP

### 3. Entrar al VPS

```bash
ssh root@IP_DEL_VPS
```

### 4. Instalar Docker en el VPS

Usa la instalación oficial de Docker para Ubuntu/Debian según tu distribución:

https://docs.docker.com/engine/install/

### 5. Preparar variables del servidor

Dentro del proyecto:

```bash
cp .env.vps.example .env.vps
nano .env.vps
```

Debes cambiar al menos:

- `DB_PASSWORD`
- `APP_SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_VENDOR_PASSWORD`

### 6. Levantar el sistema

```bash
bash scripts/vps_up.sh
```

Si todo salió bien, la aplicación queda publicada en:

```text
http://IP_DEL_VPS/
```

## Si el dump no se cargó al primer arranque

Puedes importarlo manualmente así:

```bash
bash scripts/vps_import_sql.sh deploy/vps/mysql-init/01-beta.sql
```

## Comandos útiles

Ver logs:

```bash
bash scripts/vps_logs.sh
```

Detener el stack:

```bash
bash scripts/vps_down.sh
```

## Recomendaciones mínimas

- Abre el puerto `80` en el firewall del VPS.
- No expongas el puerto `3306` públicamente.
- Si luego quieres dominio y HTTPS, se puede agregar un proxy inverso encima, pero para “mandarlo ya” con URL, la IP pública es suficiente.
