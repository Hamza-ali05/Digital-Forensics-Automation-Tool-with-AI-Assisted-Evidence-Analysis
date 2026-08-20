@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title DFAT Stop

cd /d "%~dp0"

taskkill /FI "WINDOWTITLE eq DFAT Backend" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq DFAT Frontend" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq DFAT Seed Backend" /T /F >nul 2>&1

for /f "tokens=5" %%i in ('netstat -ano 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%i /F >nul 2>&1
)
for /f "tokens=5" %%i in ('netstat -ano 2^>nul ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /PID %%i /F >nul 2>&1
)

echo DFAT stopped.
pause
exit /b 0
