@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%SCRIPT_DIR%.."

cd /d "%APP_ROOT%" || (
  echo No se pudo abrir la carpeta del proyecto.
  exit /b 1
)

docker --version >nul 2>&1 || (
  echo Docker no esta disponible.
  exit /b 1
)

echo Deteniendo servicios...
docker compose --env-file .env.docker down
if errorlevel 1 (
  echo Ocurrio un error al detener Docker Compose.
  exit /b 1
)

echo Servicios detenidos.
endlocal
