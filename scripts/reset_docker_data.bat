@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%SCRIPT_DIR%.."

cd /d "%APP_ROOT%" || (
  echo No se pudo abrir la carpeta del proyecto.
  exit /b 1
)

echo ADVERTENCIA: este comando eliminara la base de datos y respaldos en volumen Docker.
choice /M "Deseas continuar"
if errorlevel 2 (
  echo Operacion cancelada.
  exit /b 0
)

docker compose --env-file .env.docker down -v
if errorlevel 1 (
  echo Ocurrio un error al reiniciar los volumenes.
  exit /b 1
)

echo Datos Docker reiniciados.
endlocal
