@echo off
chcp 65001 >nul
where pwsh.exe >nul 2>nul
if errorlevel 1 (
  echo 请先安装 PowerShell 7：https://aka.ms/powershell-release?tag=stable
  pause
  exit /b 1
)
pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage-LinuxDo.ps1" %*
if errorlevel 1 pause
