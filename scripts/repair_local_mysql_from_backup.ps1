param(
    [string]$SnapshotPath = ""
)

$ErrorActionPreference = "Stop"

function Find-FirstExecutable {
    param(
        [string[]]$Names,
        [string[]]$CandidatePaths
    )

    foreach ($candidate in $CandidatePaths) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return [string]$cmd.Source
        }
    }
    return $null
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$EnvPath = Join-Path $RootDir ".env"
if (-not (Test-Path $EnvPath)) {
    throw "[repair] Falta $EnvPath"
}

$EnvData = @{}
Get-Content $EnvPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }
    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) {
        return
    }
    $EnvData[$parts[0].Trim()] = $parts[1]
}

$DbHost = if ($EnvData.ContainsKey("DB_HOST") -and $EnvData["DB_HOST"].Trim()) { $EnvData["DB_HOST"].Trim() } else { "127.0.0.1" }
$DbPort = if ($EnvData.ContainsKey("DB_PORT") -and $EnvData["DB_PORT"].Trim()) { $EnvData["DB_PORT"].Trim() } else { "3306" }
$DbUser = if ($EnvData.ContainsKey("DB_USER") -and $EnvData["DB_USER"].Trim()) { $EnvData["DB_USER"].Trim() } else { "root" }
$DbName = if ($EnvData.ContainsKey("DB_NAME") -and $EnvData["DB_NAME"].Trim()) { $EnvData["DB_NAME"].Trim() } else { "la_septima_estrella" }
$DbPassword = if ($EnvData.ContainsKey("DB_PASSWORD")) { $EnvData["DB_PASSWORD"] } else { "" }

if ([string]::IsNullOrWhiteSpace($SnapshotPath)) {
    $candidates = @(
        (Join-Path $RootDir "backups\latest.json"),
        "C:\Users\User\Documents\septima estrella1\backups\latest.json"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $SnapshotPath = $candidate
            break
        }
    }
}

if (-not (Test-Path $SnapshotPath)) {
    throw "[repair] No se encontró el snapshot JSON. Usa -SnapshotPath para indicar uno válido."
}

$pythonPath = Find-FirstExecutable `
    -Names @("python.exe", "python") `
    -CandidatePaths @(
        (Join-Path $RootDir ".venv\Scripts\python.exe"),
        (Join-Path $RootDir ".venvtest\Scripts\python.exe")
    )
$mysqlPath = Find-FirstExecutable `
    -Names @("mysql.exe", "mysql") `
    -CandidatePaths @(
        "C:\xampp\mysql\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        "C:\Program Files\MariaDB 11.4\bin\mysql.exe",
        "C:\Program Files\MariaDB 11.3\bin\mysql.exe",
        "C:\Program Files\MariaDB 11.2\bin\mysql.exe",
        "C:\Program Files\MariaDB 11.1\bin\mysql.exe",
        "C:\Program Files\MariaDB 11.0\bin\mysql.exe",
        "C:\Program Files\MariaDB 10.11\bin\mysql.exe"
    )

if (-not $pythonPath) {
    throw "[repair] No se encontró python del proyecto."
}
if (-not $mysqlPath) {
    throw "[repair] No se encontró mysql.exe."
}

$bootstrapScriptPath = Join-Path $RootDir "scripts\bootstrap_local_schema.py"
$restoreScriptPath = Join-Path $RootDir "scripts\restore_snapshot_local.py"
$checkScriptPath = Join-Path $RootDir "scripts\check_local_mysql_state.py"

$DbFolder = Join-Path "C:\xampp\mysql\data" $DbName
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (Test-Path $DbFolder) {
    $backupFolder = "${DbFolder}_repair_backup_$timestamp"
    Write-Host "[repair] Copiando resguardo del directorio de la base a $backupFolder"
    Copy-Item $DbFolder $backupFolder -Recurse -Force
}

$originalMysqlPwd = $env:MYSQL_PWD
$env:MYSQL_PWD = $DbPassword
try {
    Write-Host "[repair] Recreando base de datos limpia..."
    $mysqlArgs = @(
        "-h", $DbHost,
        "-P", $DbPort,
        "-u", $DbUser
    )
    & $mysqlPath @mysqlArgs -e "DROP DATABASE IF EXISTS $DbName;"
    if ($LASTEXITCODE -ne 0) {
        throw "[repair] No se pudo eliminar la base de datos dañada."
    }
    & $mysqlPath @mysqlArgs -e "CREATE DATABASE $DbName CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
    if ($LASTEXITCODE -ne 0) {
        throw "[repair] No se pudo crear la base de datos limpia."
    }

    Write-Host "[repair] Ejecutando bootstrap del esquema..."
    $bootstrapResultPath = Join-Path $RootDir ".tmp_bootstrap_result.json"
    $bootstrapProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @($bootstrapScriptPath, $bootstrapResultPath) `
        -WorkingDirectory $RootDir `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($bootstrapProcess.ExitCode -ne 0 -or -not (Test-Path $bootstrapResultPath)) {
        throw "[repair] Bootstrap falló."
    }
    Write-Host "[repair] Bootstrap OK: $(Get-Content $bootstrapResultPath -Raw -ErrorAction SilentlyContinue)"

    Write-Host "[repair] Restaurando snapshot $SnapshotPath ..."
    $restoreResultPath = Join-Path $RootDir ".tmp_restore_result.json"
    $restoreProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @($restoreScriptPath, $SnapshotPath, $restoreResultPath) `
        -WorkingDirectory $RootDir `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($restoreProcess.ExitCode -ne 0 -or -not (Test-Path $restoreResultPath)) {
        throw "[repair] La restauración del snapshot falló."
    }
    Write-Host "[repair] Restore OK: $(Get-Content $restoreResultPath -Raw -ErrorAction SilentlyContinue)"

    $stateResultPath = Join-Path $RootDir ".tmp_state_after_repair.json"
    $stateProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @($checkScriptPath, $stateResultPath) `
        -WorkingDirectory $RootDir `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($stateProcess.ExitCode -ne 0 -or -not (Test-Path $stateResultPath)) {
        throw "[repair] No se pudo verificar el estado final."
    }
    Write-Host "[repair] Estado final: $(Get-Content $stateResultPath -Raw -ErrorAction SilentlyContinue)"

    Write-Host "[repair] Base reparada y restaurada desde snapshot."
}
finally {
    if ($null -ne $originalMysqlPwd) {
        $env:MYSQL_PWD = $originalMysqlPwd
    }
    else {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
}
