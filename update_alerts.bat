@echo off
chcp 65001 >nul
rem 手动一键更新：生成今日提醒 -> 提交 -> 推送（双击运行）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_alerts.ps1"
echo.
echo 更新完成，日志见 logs\update_alerts.log
pause
