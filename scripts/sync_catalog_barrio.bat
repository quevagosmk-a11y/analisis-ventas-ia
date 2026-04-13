@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%SCRIPT_DIR%.."

cd /d "%APP_ROOT%" || (
  echo No se pudo abrir la carpeta del proyecto.
  exit /b 1
)

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo No existe .venv\Scripts\python.exe
  echo Ejecuta primero scripts\run_app.bat para crear el entorno.
  exit /b 1
)

"%VENV_PY%" src\main.py sync_barrio_catalog %*
if errorlevel 1 (
  echo Ocurrio un error al sincronizar el catalogo barrio.
  exit /b 1
)

echo.
echo Catalogo barrio sincronizado correctamente.

endlocal
