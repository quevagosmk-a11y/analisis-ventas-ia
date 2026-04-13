@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%SCRIPT_DIR%.."

cd /d "%APP_ROOT%" || (
  echo No se pudo abrir la carpeta del proyecto.
  exit /b 1
)

set "VENV_PY=.venv\Scripts\python.exe"
set "RECREATE_VENV=0"

if not exist "%VENV_PY%" (
  set "RECREATE_VENV=1"
) else (
  "%VENV_PY%" -c "import sys; print(sys.version)" >nul 2>&1
  if errorlevel 1 set "RECREATE_VENV=1"
)

if "%RECREATE_VENV%"=="1" (
  echo Entorno virtual Windows no valido o ausente. Recreando .venv...
  if exist ".venv" rmdir /s /q ".venv"
  py -3 -m venv .venv >nul 2>&1
  if errorlevel 1 (
    python -m venv .venv >nul 2>&1
    if errorlevel 1 (
      echo No se pudo crear .venv con "py -3" ni con "python".
      echo Instala Python 3 y vuelve a intentar.
      exit /b 1
    )
  )
  if not exist "%VENV_PY%" (
    echo La creacion de .venv fallo. No existe %VENV_PY%.
    exit /b 1
  )
  echo Instalando dependencias...
  "%VENV_PY%" -m pip install --upgrade pip
  if errorlevel 1 (
    echo Fallo actualizando pip.
    exit /b 1
  )
  "%VENV_PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Fallo instalando dependencias.
    exit /b 1
  )
)

"%VENV_PY%" src\main.py setup_users %*
if errorlevel 1 (
  echo Ocurrio un error al preparar usuarios base.
  exit /b 1
)

echo.
echo Usuarios base listos. Puedes iniciar la app con:
echo scripts\run_app.bat

endlocal
