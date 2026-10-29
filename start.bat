@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title CyberSecRA-X Launcher

REM ============================================================
REM  CyberSecRA-X - Windows Launcher
REM ============================================================
cd /d "%~dp0"

echo ===================================================
echo           CyberSecRA-X Launcher
echo ===================================================
echo.

REM 1. Check Python virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [*] Virtual environment not found. Setting up .venv...
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        echo Please ensure Python 3.11-3.13 is installed and added to PATH.
        goto ERROR_EXIT
    )
    echo [*] Installing Python requirements...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-documents.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        goto ERROR_EXIT
    )
    echo [OK] Python dependencies installed.
    echo.
)

REM 2. Check frontend dependencies
if not exist "frontend\node_modules" (
    echo [*] Frontend dependencies not found. Installing node_modules...
    call npm ci --prefix frontend
    if errorlevel 1 (
        echo [ERROR] Failed to install npm dependencies.
        goto ERROR_EXIT
    )
    echo [OK] Frontend dependencies installed.
    echo.
)

REM 3. Check frontend build
if not exist "frontend\.next\BUILD_ID" (
    echo [*] Production build not found. Building Next.js frontend...
    .venv\Scripts\python.exe scripts\product.py build
    if errorlevel 1 (
        echo [ERROR] Frontend build failed.
        goto ERROR_EXIT
    )
    echo [OK] Frontend built successfully.
    echo.
)

REM 4. Launch backend and frontend
echo [*] Starting CyberSecRA-X services...
echo [*] The dashboard will open automatically in your browser.
echo.
.venv\Scripts\python.exe scripts\product.py up --no-build
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start services.
    goto ERROR_EXIT
)

echo.
echo ===================================================
echo   CyberSecRA-X is running!
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000
echo ===================================================
echo   [STATUS] Online and serving.
echo   Keep this window open while using the dashboard.
echo.
echo   To shut down services, type Q and press Enter:
echo ===================================================
echo.

:WAIT_LOOP
set "USER_INPUT="
set /p USER_INPUT="CyberSecRA-X (type Q to stop) > "
if /i "!USER_INPUT!"=="q" goto STOP_SERVICES
if /i "!USER_INPUT!"=="quit" goto STOP_SERVICES
if /i "!USER_INPUT!"=="stop" goto STOP_SERVICES
if /i "!USER_INPUT!"=="exit" goto STOP_SERVICES
goto WAIT_LOOP

:STOP_SERVICES
echo.
echo [*] Stopping CyberSecRA-X services...
.venv\Scripts\python.exe scripts\product.py down
echo [OK] All services stopped.
ping 127.0.0.1 -n 3 >nul
exit /b 0

:ERROR_EXIT
echo.
echo ===================================================
echo   [ERROR] An error occurred while launching.
echo   Check the messages above for details.
echo ===================================================
echo.
pause
exit /b 1

