param(
    [Parameter(Mandatory = $true)] [string]$ProjectDir,
    [Parameter(Mandatory = $true)] [string]$EnvFile,
    [string]$PythonExe = "python",
    [string]$LogDir = "C:\ProgramData\MSConnect\logs"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "MSConnect env file not found: $EnvFile"
}

# Export simple KEY=VALUE entries. Quoted values are accepted; comments and
# blank lines are ignored. Secrets stay in the operator-owned env file.
Get-Content -LiteralPath $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($Matches[1], $value, "Process")
    }
}

Set-Location -LiteralPath $ProjectDir
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $LogDir "watcher-$stamp.log"

& $PythonExe manage.py run_watcher_agent --match-run-by-name *>&1 |
    Tee-Object -FilePath $logPath -Append
exit $LASTEXITCODE
