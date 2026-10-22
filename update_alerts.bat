@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_alerts.ps1"
if errorlevel 1 (
  echo 更新失败，请查看 logsuto_update.log
) else (
  echo 更新成功或已有任务正在运行，详情见 logsuto_update.log
)
pause
