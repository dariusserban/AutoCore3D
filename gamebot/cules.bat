@echo off
setlocal
title cules automat
cd /d "%~dp0.."

set PYEXE=gamebot\.venv\Scripts\python.exe
if not exist "%PYEXE%" (
    echo Nu gasesc mediul virtual. Ruleaza intai instalare.bat
    echo.
    pause
    exit /b 1
)

"%PYEXE%" -u -m gamebot.main pickup --profile gamebot\profiles\drakensang.yaml
echo.
pause
