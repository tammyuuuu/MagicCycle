# -*- coding: utf-8 -*-
# 本地一键刷新"今日提醒"：不需要 VPN、不推送 GitHub
# ---------------------------------------------------------------
# 做两件事：
#   1) 调用 export_alerts.py 增量拉最新行情（东财为主，失败自动切新浪）；
#   2) 重新生成 docs/index.html，并把「页面数据日」打在屏幕上。
# 用法：双击 refresh_local.bat，或：
#   powershell -NoProfile -ExecutionPolicy Bypass -File refresh_local.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File refresh_local.ps1 -NoPause
param([switch]$NoPause, [int]$WaitNetMinutes = 0)

$ErrorActionPreference = 'Continue'

$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $proj

$logDir = Join-Path $proj 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$log = Join-Path $logDir 'refresh_local.log'
# 统一用 UTF-8 无 BOM 写日志，避免 PS5.1 的 *>> 写出 UTF-16 导致日志乱码
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    [IO.File]::AppendAllText($log, $line + [Environment]::NewLine, $utf8)
}

Write-Log '===== 本地刷新开始（不推送）====='

if ($WaitNetMinutes -gt 0) {
    # 校园网要手动点连接，可能拖很久；自动启动时先等网络可用再抓数
    # （手动双击默认 -WaitNetMinutes 0，不等待）
    # 探测间隔可调：越大越“安静”，越小越及时
    $probeIntervalSec = 60
    $probe = 'https://qt.gtimg.cn/q=sh510500'
    $deadline = (Get-Date).AddMinutes($WaitNetMinutes)
    $n = 0
    $netOk = $false
    while (-not $netOk -and (Get-Date) -lt $deadline) {
        $n++
        try {
            $netOk = (Invoke-WebRequest -Uri $probe -TimeoutSec 8 `
                -UseBasicParsing).StatusCode -eq 200
        } catch { $netOk = $false }
        if (-not $netOk) { Start-Sleep -Seconds $probeIntervalSec }
    }
    if ($netOk) {
        Write-Log "网络已就绪（第 $n 次探测），开始抓数"
    } else {
        Write-Log "等网络超时（$WaitNetMinutes 分钟 / $n 次），用旧缓存继续"
    }
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = 'D:\loaddown\python\python.exe' }

$sw = [Diagnostics.Stopwatch]::StartNew()
& $py 'export_alerts.py' *>&1 | ForEach-Object { Write-Log "$_" }
$exitCode = $LASTEXITCODE
$sw.Stop()
$secs = [int]$sw.Elapsed.TotalSeconds

if ($exitCode -ne 0) {
    Write-Log "生成失败（退出码 $exitCode，耗时 ${secs}s）。网络或数据源可能不通，稍后重试。"
    if (-not $NoPause) { Read-Host '按回车键退出' | Out-Null }
    exit $exitCode
}

# 从生成好的页面里读出数据日，方便一眼确认是否真的刷新了
$page = Join-Path $proj 'docs\index.html'
$dates = @()
if (Test-Path $page) {
    $html = [IO.File]::ReadAllText($page, [Text.Encoding]::UTF8)
    $dates = [regex]::Matches($html, '数据日 (\d{4}-\d{2}-\d{2})') |
        ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
}

Write-Log ("生成成功（耗时 ${secs}s）；页面数据日：" + ($(if ($dates) { $dates -join '、' } else { '未识别' })))
Write-Log '本地页面：docs\index.html —— 浏览器里按 Ctrl+F5 强刷即可'
Write-Log '===== 完成 ====='

if (-not $NoPause) { Read-Host '按回车键退出' | Out-Null }
exit 0
