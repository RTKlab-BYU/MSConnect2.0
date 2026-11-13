param(
    [Parameter(Mandatory = $true)] [string]$ProjectDir,
    [Parameter(Mandatory = $true)] [string]$EnvFile,
    [Parameter(Mandatory = $true)] [string]$WslProjectDir,
    [string]$Distro = "Ubuntu",
    [string]$TaskName = "MSConnect DIA-NN Processor"
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $ProjectDir "ops\run-msconnect-diann-processor.ps1"
if (-not (Test-Path -LiteralPath $runner)) { throw "Processor runner not found: $runner" }
if (-not (Test-Path -LiteralPath $EnvFile)) { throw "Processor env file not found: $EnvFile" }

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -ProjectDir `"$ProjectDir`" -EnvFile `"$EnvFile`" -WslProjectDir `"$WslProjectDir`" -Distro `"$Distro`" -Action run"
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $actionArgs -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$restart = New-ScheduledTaskSettingsSet -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $restart -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started: $TaskName"
Write-Host "WSL distribution: $Distro"
Write-Host "The configured Windows user must be signed in for WSL2 to run."
Write-Host "Check: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
