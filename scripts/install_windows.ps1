#Requires -Version 5.1
<#
.SYNOPSIS
  Configura el entorno de la aplicación en Windows (venv, dependencias y tarea programada).

.PARAMETER Python
  Ejecutable de Python a utilizar (por defecto 'python').

.PARAMETER TaskName
  Nombre de la tarea programada para limpiar sesiones (por defecto AnalisisVentas_Cleanup).

.PARAMETER SkipTask
  Si se especifica, omite la creación de la tarea programada.
#>
param(
    [string]$Python = "python",
    [string]$TaskName = "AnalisisVentas_Cleanup",
    [switch]$SkipTask
)

$ErrorActionPreference = "Stop"

function Write-Info($message) { Write-Host ">> $message" -ForegroundColor Cyan }
function Write-WarningMessage($message) { Write-Warning $message }

$scriptPath = $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptPath)
Write-Info "Directorio del proyecto: $repoRoot"

# Validar Python
try {
    $pythonVersion = & $Python --version
    Write-Info "Python detectado: $pythonVersion"
} catch {
    Write-Error "No se pudo ejecutar '$Python'. Instala Python 3.10+ y vuelve a intentarlo."
    exit 1
}

# Crear entorno virtual si no existe
$venvPath = Join-Path $repoRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Info "Creando entorno virtual en $venvPath"
    & $Python -m venv $venvPath
} else {
    Write-Info "Entorno virtual existente reutilizado."
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

# Actualizar pip e instalar dependencias
Write-Info "Actualizando pip..."
& $venvPython -m pip install --upgrade pip

$requirements = Join-Path $repoRoot "requirements.txt"
if (Test-Path $requirements) {
    Write-Info "Instalando dependencias desde requirements.txt"
    & $venvPython -m pip install -r $requirements
} else {
    Write-WarningMessage "Archivo requirements.txt no encontrado, omitiendo instalación de dependencias."
}

# Crear carpeta de logs
$logsDir = Join-Path $repoRoot "logs"
if (-not (Test-Path $logsDir)) {
    Write-Info "Creando carpeta de logs en $logsDir"
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

# Crear tarea programada para limpiar sesiones
if (-not $SkipTask) {
    $cleanupScript = Join-Path $repoRoot "src\main.py"
    $taskCommand = "cmd /c `"" + $venvPython + "`" `"" + $cleanupScript + "`" cleanup_sessions`""
    Write-Info "Registrando tarea programada '$TaskName' para ejecutar limpieza cada hora."
    schtasks /Create /TN $TaskName /SC HOURLY /F /TR $taskCommand | Out-Null
}

# Mensajes finales
Write-Host ""
Write-Host "== Instalación completada ==" -ForegroundColor Green
Write-Host "1. Crea o ajusta el archivo '.env' (puedes usar '.env.example' como base)." -ForegroundColor Yellow
Write-Host "2. Para iniciar la aplicación usa: scripts\run_app.bat" -ForegroundColor Yellow
if (-not $SkipTask) {
    Write-Host "3. La tarea programada '$TaskName' limpiará sesiones cada hora. Verifica con: schtasks /Query /TN `$TaskName`" -ForegroundColor Yellow
}
