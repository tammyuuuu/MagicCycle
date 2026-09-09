# -*- coding: utf-8 -*-
# 自动更新"今日提醒"静态页：生成 docs/index.html -> 提交 -> 推送到 GitHub Pages
# 由 Windows 计划任务调用（登录时 / 每天16:00），也可手动运行。
# 开机后先等 90 秒，等网络就绪；无变化时自动忽略，不影响退出码。
$ErrorActionPreference = 'Continue'

$proj = 'd:\file\fun\invest\cycle'
$logDir = Join-Path $proj 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$log = Join-Path $logDir 'update_alerts.log'
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
"[$ts] ===== 开始自动更新 =====" | Out-File $log -Append -Encoding utf8

Start-Sleep -Seconds 90   # 等系统网络就绪

try {
    Set-Location $proj

    # python（找不到就用绝对路径兜底）
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = 'D:\loaddown\python\python.exe' }

    "  -> 生成今日提醒页面" | Out-File $log -Append -Encoding utf8
    & $py export_alerts.py *>> $log

    "  -> git add / commit / push" | Out-File $log -Append -Encoding utf8
    git add docs/index.html 2>> $log
    git commit -m "auto update alerts $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>> $log
    git push 2>> $log

    "[$ts] ===== 完成 =====" | Out-File $log -Append -Encoding utf8
}
catch {
    "[$ts] 错误：$_" | Out-File $log -Append -Encoding utf8
}
