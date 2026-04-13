@echo off
setlocal

cd /d "%~dp0\.."
set "PYTHON_BIN=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_BIN=.venv\Scripts\python.exe"

echo [1/5] Verificando sintaxis Python...
"%PYTHON_BIN%" -m compileall -q src
if errorlevel 1 (
  echo ERROR: Fallo en compileall de Python.
  exit /b 1
)

echo [2/5] Ejecutando tests Python...
"%PYTHON_BIN%" -m pytest -q
if errorlevel 1 (
  echo ERROR: Fallo en pytest.
  exit /b 1
)

echo [3/5] Ejecutando ruff...
"%PYTHON_BIN%" -m ruff check src tests
if errorlevel 1 (
  echo ERROR: Ruff detecto problemas de lint.
  exit /b 1
)

echo [4/5] Verificando sintaxis frontend...
npm run -s check:main
if errorlevel 1 (
  echo ERROR: Fallo en check:main.
  exit /b 1
)

echo [5/5] Verificando formato frontend...
npx --yes prettier --check "src/frontend/**/*.{js,css,html}"
if errorlevel 1 (
  echo ERROR: Hay archivos frontend sin formato.
  exit /b 1
)

echo [5/5] Verificacion completada OK.
exit /b 0
