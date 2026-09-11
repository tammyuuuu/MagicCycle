' 登录后静默刷新"ETF 今日提醒"本地页面
' ------------------------------------------------------------------
' 放在 Windows「启动」文件夹里，登录后自动执行（无需管理员、无需 VPN、不推送 GitHub）。
' 作用：等 90 秒让网络就绪 -> 隐藏窗口运行 refresh_local.ps1 -NoPause
' 结果看 logs\refresh_local.log；本地页面 docs\index.html
Option Explicit

Dim sh, base, ps1, cmd
Set sh = CreateObject("WScript.Shell")

base = "d:\file\fun\invest\cycle"
ps1  = base & "\refresh_local.ps1"

' 登录瞬间网络常常还没就绪（校园网要几分钟），交给 ps1 自己探测：最多等 10 分钟
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """ -NoPause -WaitNetMinutes 10"
' 第二个参数 0 = 隐藏窗口，第三个 False = 不等待
sh.Run cmd, 0, False
