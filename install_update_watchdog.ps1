# Independent trigger only: never regenerates or commits local market data.
$ErrorActionPreference = 'Stop'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$python = (Get-Command python -ErrorAction Stop).Source
[IO.File]::WriteAllText((Join-Path $PSScriptRoot '.watchdog-python.txt'), $python)
$triggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '16:47'),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '18:47'),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '20:47'),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '22:47'),
    (New-ScheduledTaskTrigger -AtLogOn -User $user)
)
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'Expected Windows timezone China Standard Time; configure task times explicitly before installing' }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot 'run_update_watchdog.ps1') + '"') -WorkingDirectory $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CycleMarketUpdateWatchdog' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'Check published Cycle data and dispatch GitHub workflow if stale; requires logged-in user and network' -Force
