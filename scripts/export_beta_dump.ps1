param(
    [string]$OutFile = ""
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
if ([string]::IsNullOrWhiteSpace($OutFile)) {
    $OutFile = Join-Path $RootDir "deploy\railway\beta_dump.sql"
}

$EnvPath = Join-Path $RootDir ".env"
if (-not (Test-Path $EnvPath)) {
    throw "[dump] Falta $EnvPath"
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
    $key = $parts[0].Trim()
    $value = $parts[1]
    $EnvData[$key] = $value
}

$DbHost = if ($EnvData.ContainsKey("DB_HOST") -and $EnvData["DB_HOST"].Trim()) { $EnvData["DB_HOST"].Trim() } else { "127.0.0.1" }
$DbPort = if ($EnvData.ContainsKey("DB_PORT") -and $EnvData["DB_PORT"].Trim()) { $EnvData["DB_PORT"].Trim() } else { "3306" }
$DbUser = if ($EnvData.ContainsKey("DB_USER") -and $EnvData["DB_USER"].Trim()) { $EnvData["DB_USER"].Trim() } else { "root" }
$DbName = if ($EnvData.ContainsKey("DB_NAME") -and $EnvData["DB_NAME"].Trim()) { $EnvData["DB_NAME"].Trim() } else { "la_septima_estrella" }
$DbPassword = if ($EnvData.ContainsKey("DB_PASSWORD")) { $EnvData["DB_PASSWORD"] } else { "" }

$ignoreTables = @(
    "auditoria_eventos",
    "configuracion_app",
    "roles_permisos",
    "schema_migrations",
    "sesiones_activas",
    "sistema_configuracion",
    "tabla_logs_ia",
    "producto_precio_auditoria"
)

$mysqldumpCandidatePaths = @(
    "C:\xampp\mysql\bin\mysqldump.exe",
    "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe",
    "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
    "C:\Program Files\MariaDB 11.4\bin\mysqldump.exe",
    "C:\Program Files\MariaDB 11.3\bin\mysqldump.exe",
    "C:\Program Files\MariaDB 11.2\bin\mysqldump.exe",
    "C:\Program Files\MariaDB 11.1\bin\mysqldump.exe",
    "C:\Program Files\MariaDB 11.0\bin\mysqldump.exe",
    "C:\Program Files\MariaDB 10.11\bin\mysqldump.exe"
)

$pythonCandidatePaths = @(
    (Join-Path $RootDir ".venv\Scripts\python.exe"),
    (Join-Path $RootDir ".venvtest\Scripts\python.exe")
)
$pythonPath = Find-FirstExecutable -Names @("python.exe", "python") -CandidatePaths $pythonCandidatePaths
$mysqldumpPath = Find-FirstExecutable -Names @("mysqldump.exe", "mysqldump") -CandidatePaths $mysqldumpCandidatePaths

if (-not $mysqldumpPath) {
    throw "[dump] mysqldump no esta disponible. Instala MySQL Client, XAMPP o MariaDB Client."
}
if (-not $pythonPath) {
    throw "[dump] python no esta disponible para inspeccionar las tablas."
}

$OutDir = Split-Path -Parent $OutFile
if ($OutDir) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

$originalMysqlPwd = $env:MYSQL_PWD
$env:MYSQL_PWD = $DbPassword
try {
    $healthyTables = @()
    $omittedTables = @($ignoreTables)

    $probeScriptPath = Join-Path $env:TEMP ("codex-db-probe-" + [guid]::NewGuid().ToString("N") + ".py")
    @'
import json
import sys
import pymysql

host = sys.argv[1]
port = int(sys.argv[2])
user = sys.argv[3]
password = "" if sys.argv[4] == "__EMPTY__" else sys.argv[4]
database = sys.argv[5]
ignored = set(filter(None, sys.argv[6].split(",")))

payload = {"ok": True, "healthy": [], "broken": [], "error": ""}

try:
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    table_names = [row[0] for row in cur.fetchall()]
    for table_name in table_names:
        if table_name in ignored:
            continue
        try:
            cur.execute(f"SHOW CREATE TABLE `{table_name}`")
            cur.fetchone()
            payload["healthy"].append(table_name)
        except Exception:
            payload["broken"].append(table_name)
    cur.close()
    conn.close()
except Exception as exc:
    payload["ok"] = False
    payload["error"] = str(exc)

print(json.dumps(payload, ensure_ascii=False))
'@ | Set-Content -Encoding UTF8 $probeScriptPath

    $probeStdout = Join-Path $env:TEMP ("codex-db-probe-" + [guid]::NewGuid().ToString("N") + ".out.txt")
    $probeStderr = Join-Path $env:TEMP ("codex-db-probe-" + [guid]::NewGuid().ToString("N") + ".err.txt")
    $probePasswordArg = if ([string]::IsNullOrEmpty($DbPassword)) { "__EMPTY__" } else { $DbPassword }
    try {
        $probeProcess = Start-Process `
            -FilePath $pythonPath `
            -ArgumentList @($probeScriptPath, $DbHost, $DbPort, $DbUser, $probePasswordArg, $DbName, ($ignoreTables -join ",")) `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $probeStdout `
            -RedirectStandardError $probeStderr
        $probeExit = $probeProcess.ExitCode
        $probeOutput = if (Test-Path $probeStdout) { Get-Content $probeStdout -Raw -ErrorAction SilentlyContinue } else { "" }
        $probeError = if (Test-Path $probeStderr) { Get-Content $probeStderr -Raw -ErrorAction SilentlyContinue } else { "" }
    }
    finally {
        Remove-Item $probeScriptPath -Force -ErrorAction SilentlyContinue
        Remove-Item $probeStdout -Force -ErrorAction SilentlyContinue
        Remove-Item $probeStderr -Force -ErrorAction SilentlyContinue
    }

    if ($probeExit -ne 0 -or -not $probeOutput) {
        $probeDetail = ($probeError | Out-String).Trim()
        if (-not $probeDetail) {
            $probeDetail = ($probeOutput | Out-String).Trim()
        }
        if (-not $probeDetail) {
            $probeDetail = "Sin salida de diagnostico."
        }
        throw "[dump] No se pudieron listar las tablas exportables. $probeDetail"
    }

    $probePayload = ($probeOutput | Out-String | ConvertFrom-Json)
    if (-not $probePayload.ok) {
        throw "[dump] No se pudieron listar las tablas: $($probePayload.error)"
    }

    $healthyTables = @($probePayload.healthy)
    $omittedTables += @($probePayload.broken)

    if (-not $healthyTables -or $healthyTables.Count -eq 0) {
        throw "[dump] No se encontraron tablas exportables. La base necesita reparacion antes del dump."
    }

    $args = @(
        "-h", $DbHost,
        "-P", $DbPort,
        "-u", $DbUser,
        "--result-file=$OutFile",
        "--routines",
        "--triggers",
        "--single-transaction",
        "--skip-lock-tables",
        $DbName
    )
    foreach ($tableName in $healthyTables) {
        $args += $tableName
    }
    $process = Start-Process `
        -FilePath $mysqldumpPath `
        -ArgumentList $args `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($process.ExitCode -ne 0) {
        throw "[dump] mysqldump terminó con código $($process.ExitCode)."
    }

    $script:DumpOmittedTables = $omittedTables | Sort-Object -Unique
    $script:DumpHealthyCount = $healthyTables.Count
}
finally {
    if ($null -ne $originalMysqlPwd) {
        $env:MYSQL_PWD = $originalMysqlPwd
    }
    else {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
}

Write-Host "[dump] Exportado en $OutFile"
Write-Host "[dump] Tablas exportadas: $script:DumpHealthyCount"
if ($script:DumpOmittedTables -and $script:DumpOmittedTables.Count -gt 0) {
    Write-Host "[dump] Tablas omitidas: $($script:DumpOmittedTables -join ', ')"
}
