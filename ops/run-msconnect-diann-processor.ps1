param(
    [Parameter(Mandatory = $true)] [string]$ProjectDir,
    [Parameter(Mandatory = $true)] [string]$EnvFile,
    [Parameter(Mandatory = $true)] [string]$WslProjectDir,
    [string]$Distro = "Ubuntu",
    [ValidateSet("check", "run", "once")] [string]$Action = "run"
)

$ErrorActionPreference = "Stop"
foreach ($path in @($ProjectDir, $EnvFile)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Path not found: $path" }
}
$runner = Join-Path $ProjectDir "ops\msconnect_diann_processor.py"
if (-not (Test-Path -LiteralPath $runner)) { throw "Processor CLI not found: $runner" }

$linuxEnv = (& wsl.exe --distribution $Distro --exec wslpath -a $EnvFile).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxEnv) { throw "Could not map env file path into WSL2." }

& wsl.exe --distribution $Distro --exec python3 "$WslProjectDir/ops/msconnect_diann_processor.py" $Action --env-file $linuxEnv --project-dir $WslProjectDir
exit $LASTEXITCODE
