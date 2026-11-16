$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$logDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$python = Join-Path $PSScriptRoot '.watchdog-python.txt'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run install_update_watchdog.ps1 first' }
$exe = (Get-Content -LiteralPath $python -Raw).Trim()
& $exe -u (Join-Path $PSScriptRoot 'update_watchdog.py') *>> (Join-Path $logDir 'update_watchdog.log')
exit $LASTEXITCODE
