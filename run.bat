@echo off
chcp 65001 >nul
title QSerial - PySide6 Qt
echo ===================================
echo   QSerial Serial Debugging Tool
echo   PySide6 / Qt - Development Mode
echo ===================================
echo.

echo [1/4] Generating version file...
python3 scripts/generate_version.py
if errorlevel 1 (
    echo Error: Failed to generate the version file.
    pause
    exit /b 1
)
echo.

echo [2/4] Checking dependencies...
python3 -c "import serial, PySide6" 2>nul
if errorlevel 1 (
    echo Warning: Required dependencies are missing.
    echo Installing dependencies...
    pip3 install -r requirements.txt
    if errorlevel 1 (
        echo Error: Dependency installation failed.
        pause
        exit /b 1
    )
)
echo.

echo [3/4] Generating translations...
python3 scripts/generate_translations.py
if errorlevel 1 (
    echo Error: Translation generation failed.
    pause
    exit /b 1
)
echo.

echo [4/4] Starting the application...
python3 src/main/app_qt.py

echo.
echo Application exited.
