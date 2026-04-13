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
  echo Activa o crea el entorno virtual primero.
  exit /b 1
)

"%VENV_PY%" scripts\load_product_images_open.py --recrop-existing --target-size 320 %*
if errorlevel 1 (
  echo Ocurrio un error al recortar imagenes.
  exit /b 1
)

echo.
echo Recorte completado correctamente.
endlocal
