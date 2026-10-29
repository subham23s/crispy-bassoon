@echo off
chcp 65001 >nul
title Stop CyberSecRA-X
cd /d "%~dp0"

echo Stopping CyberSecRA-X services...
.venv\Scripts\python.exe scripts\product.py down
echo.
pause
