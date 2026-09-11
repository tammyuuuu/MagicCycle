# -*- coding: utf-8 -*-
# 自动更新"今日提醒"静态页：生成 docs/index.html -> 提交 -> 推送到 GitHub Pages
# 由 Windows 计划任务调用（登录时 / 每天16:00），也可手动运行。
# 开机/登录后先探测网络（校园网要几分钟才通），一通就生成并推送；无变化时自动忽略。
$ErrorActionPreference = 'Continue'

$proj = 'd:\file\fun\invest\cycle'
$logDir = Join-Path $proj 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$log = Join-Path $logDir 'update_alerts.log'
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
"[$ts] ===== 开始自动更新 =====" | Out-File $log -Append -Encoding utf8

# 等网络真正可用：校园网需要手动点连接，可能拖很久，所以间隔拉长、总时长放宽。
# 下面两个数可以按习惯调：间隔越小越及时，越大越“安静”。
$probeIntervalSec = 60      # 每隔多少秒探一次
$maxWaitMinutes   = 10      # 最多等多少分钟（超时就用旧缓存继续跑）

$probe = 'https://qt.gtimg.cn/q=sh510500'
$deadline = (Get-Date).AddMinutes($maxWaitMinutes)
$n = 0
$netOk = $false
while (-not $netOk -and (Get-Date) -lt $deadline) {
    $n++
    try {
        $r = Invoke-WebRequest -Uri $probe -TimeoutSec 8 -UseBasicParsing
        $netOk = ($r.StatusCode -eq 200)
    } catch {
        $netOk = $false
    }
    if (-not $netOk) { Start-Sleep -Seconds $probeIntervalSec }
}
if ($netOk) {
    "[$(Get-Date -Format 'HH:mm:ss')] 网络已就绪（第 $n 次探测），开始抓数" |
        Out-File $log -Append -Encoding utf8
} else {
    "[$(Get-Date -Format 'HH:mm:ss')] 等网络超时（$maxWaitMinutes 分钟 / $n 次），用旧缓存继续" |
        Out-File $log -Append -Encoding utf8
}

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
