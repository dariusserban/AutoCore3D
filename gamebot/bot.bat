@echo off
setlocal
title gamebot
cd /d "%~dp0.."

set PYEXE=gamebot\.venv\Scripts\python.exe
if not exist "%PYEXE%" (
    echo Nu gasesc mediul virtual. Ruleaza intai instalare.bat
    echo.
    pause
    exit /b 1
)

"%PYEXE%" -m gamebot.main gui
if errorlevel 1 (
    echo.
    echo Fereastra nu a pornit. Daca scrie ceva de "tkinter", reinstaleaza
    echo Python de la python.org - instalarea standard il include.
    echo.
    echo Pana atunci poti folosi meniul din meniu.bat
    echo.
    pause
)
