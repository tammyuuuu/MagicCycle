@echo off
chcp 65001 >nul
rem 本地一键刷新"今日提醒"（生成 docs\index.html），不推送 GitHub、不需要 VPN
rem 双击运行即可；日志见 logs\refresh_local.log
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh_local.ps1"
