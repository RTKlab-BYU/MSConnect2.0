param(
    [Parameter(Mandatory = $true)] [string]$ProjectDir,
    [Parameter(Mandatory = $true)] [string]$EnvFile,
    [string]$PythonExe = "python",
    [string]$TaskName = "MSConnect Watcher",
    [string]$LogDir = "C:\ProgramData\MSConnect\logs"
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $ProjectDir "ops\run-msconnect-watcher.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Watcher runner not found: $runner"
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "MSConnect env file not found: $EnvFile"
}

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -ProjectDir `"$ProjectDir`" -EnvFile `"$EnvFile`" -PythonExe `"$PythonExe`" -LogDir `"$LogDir`""
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $actionArgs -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$restart = New-ScheduledTaskSettingsSet -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $restart -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started: $TaskName"
Write-Host "Logs: $LogDir"
Write-Host "Check: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
