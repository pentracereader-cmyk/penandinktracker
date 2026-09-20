@echo off
setlocal enabledelayedexpansion
title Pen ^& Ink Tracker
cd /d "%~dp0"

echo Pen ^& Ink Tracker - checking that Python is installed...
echo.

set "PYEXE="

python --version >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=python"
) else (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py -3"
    )
)

if "%PYEXE%"=="" (
    echo Python was not found on this computer.
    echo.
    echo Pen ^& Ink Tracker needs Python 3 to run. It is free and takes about
    echo a minute to install:
    echo.
    echo     https://www.python.org/downloads/
    echo.
    echo IMPORTANT: on the Python installer's first screen, tick the box
    echo that says "Add python.exe to PATH" before clicking Install.
    echo.
    echo Once Python is installed, run this file again.
    echo.
    pause
    exit /b 1
)

echo Found Python:
%PYEXE% --version
echo.

echo Running first-time setup (only asks questions the first time)...
%PYEXE% setup_first_run.py
if errorlevel 1 (
    echo.
    echo First-run setup reported a problem - see above.
    pause
    exit /b 1
)

echo.
echo Starting the Pen ^& Ink Tracker server...
echo (Leave this window open while you use the app. Close it to stop the app.)
echo.

start "" http://localhost:3838

%PYEXE% server.py

echo.
echo The server has stopped.
pause
