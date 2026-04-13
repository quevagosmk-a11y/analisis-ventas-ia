@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%SCRIPT_DIR%.."

cd /d "%APP_ROOT%" || (
  echo No se pudo abrir la carpeta del proyecto.
  exit /b 1
)

docker --version >nul 2>&1 || (
  echo Docker no esta disponible. Instala Docker Desktop y vuelve a intentar.
  exit /b 1
)

if not exist ".env.docker" (
  if exist ".env.docker.example" (
    copy /Y ".env.docker.example" ".env.docker" >nul
    echo Se creo ".env.docker" con valores de ejemplo.
    echo Edita ".env.docker" para cambiar claves antes de produccion.
  )
)

echo Levantando servicios...
docker compose --env-file .env.docker up -d --build
if errorlevel 1 (
  echo Ocurrio un error al iniciar Docker Compose.
  exit /b 1
)

echo Servicios iniciados.
echo URL: http://localhost:5000
start "" "http://localhost:5000"

endlocal
