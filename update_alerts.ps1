# Automatic snapshot generation and publication at Windows login.
param([int]$WaitNetMinutes = 10)
$ErrorActionPreference = 'Stop'
$proj = $PSScriptRoot
Set-Location -LiteralPath $proj
$logDir = Join-Path $proj 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'auto_update.log'
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Write-Log([string]$message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    [IO.File]::AppendAllText($log, $line + [Environment]::NewLine, $utf8)
    Write-Host $line
}
function Invoke-Logged([string]$program, [string[]]$arguments) {
    # Windows PowerShell 5 treats native stderr as ErrorRecord, even on success.
    $ErrorActionPreference = 'Continue'
    & $program @arguments 2>&1 | ForEach-Object { Write-Log "$_" }
    if ($LASTEXITCODE -ne 0) { throw "$program failed: exit $LASTEXITCODE" }
}
# Prevent overlapping startup/manual runs in this checkout.
$lock = $null
try {
    $lock = [IO.File]::Open((Join-Path $logDir 'auto_update.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
} catch { Write-Log 'Another update is running; skipped.'; exit 0 }
try {
    Write-Log "START project=$proj"
    $deadline = (Get-Date).AddMinutes($WaitNetMinutes)
    do {
        $ready = $false
        try { $ready = (Invoke-WebRequest -UseBasicParsing -Uri 'https://qt.gtimg.cn/q=sh510500' -TimeoutSec 8).StatusCode -eq 200 } catch {}
        if ($ready -or (Get-Date) -ge $deadline) { break }
        Start-Sleep -Seconds 30
    } while ($true)
    if (-not $ready) { throw 'Network unavailable; no snapshot published. Retry update_alerts.bat after connecting.' }
    $env:GIT_TERMINAL_PROMPT = '0'
    $gitExe = (Get-Command git -ErrorAction Stop).Source
    $gitRoot = Split-Path (Split-Path $gitExe -Parent) -Parent
    $bundledSsh = Join-Path $gitRoot 'usr\bin\ssh.exe'
    if (Test-Path -LiteralPath $bundledSsh) {
        $env:SHELL = (Join-Path $gitRoot 'usr\bin\sh.exe').Replace('\', '/')
        $sshPath = $bundledSsh.Replace('\', '/')
        $env:GIT_SSH_COMMAND = '"' + $sshPath + '" -o BatchMode=yes -o ConnectTimeout=20'
    } else {
        $env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes -o ConnectTimeout=20'
    }
    $env:PYTHONIOENCODING = 'utf-8'
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = [Console]::OutputEncoding
    $py = (Get-Command python -ErrorAction Stop).Source
    Write-Log 'Generating snapshot...'
    Invoke-Logged $py @('-u', (Join-Path $proj 'export_alerts.py'))
    $snapshot = Get-Content -LiteralPath 'docs/index.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not @($snapshot | Where-Object { $_.status -ne 'error' }).Count) { throw 'All assets failed; refusing to publish.' }
    $dates = @($snapshot | ForEach-Object { $_.date } | Where-Object { $_ } | Sort-Object -Unique)
    Write-Log ('Snapshot data dates: ' + ($dates -join ', '))
    $html = [IO.File]::ReadAllText((Join-Path $proj 'docs/index.html'))
    if ($html.Contains('stale') -or $html.Contains([string][char]0x26A0)) { Write-Log 'WARNING: see page for cached-data or other warnings; generation time is not market-data time.' }
    # The HTML references immutable bundles; publish the complete offline release together.
    $publishPaths = @('docs/index.html', 'docs/index.json', 'docs/purchase_monitor.json', 'docs/account_nav.json', 'docs/assets', 'docs/bundle-assets.json', 'docs/pwa-manifest.json', 'docs/sw.js', 'docs/pwa.js')
    Invoke-Logged 'git' (@('add', '--') + $publishPaths)
    & git diff --cached --quiet -- @publishPaths
    $diffCode = $LASTEXITCODE
    if ($diffCode -eq 1) {
        Invoke-Logged 'git' (@('commit', '--only', '-m', "auto update alerts $(Get-Date -Format 'yyyy-MM-dd HH:mm')", '--') + $publishPaths)
    } elseif ($diffCode -ne 0) { throw 'git diff failed' }
    Invoke-Logged 'git' @('push')
    Write-Log 'SUCCESS: snapshot pushed to GitHub; Pages deployment follows.'
} catch {
    Write-Log "FAILED: $_"
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
