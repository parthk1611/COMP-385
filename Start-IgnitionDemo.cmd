@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-IgnitionDemo.ps1"
if errorlevel 1 pause
