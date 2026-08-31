@echo off
setlocal
title gamebot - instalare
cd /d "%~dp0.."

echo ===============================================
echo   gamebot - instalare (se ruleaza o singura data)
echo ===============================================
echo.

REM --- Cautam Python ---------------------------------------------------
set PY=
where py >nul 2>&1 && set PY=py -3
if "%PY%"=="" (
    where python >nul 2>&1 && set PY=python
)
if "%PY%"=="" (
    echo EROARE: nu gasesc Python pe calculator.
    echo.
    echo Descarca-l de la https://www.python.org/downloads/
    echo La instalare BIFEAZA casuta "Add python.exe to PATH".
    echo Apoi ruleaza din nou fisierul asta.
    echo.
    pause
    exit /b 1
)

echo Python gasit: 
%PY% --version
echo.

REM --- Verificam versiunea (minim 3.10) --------------------------------
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo EROARE: ai o versiune prea veche de Python. E nevoie de 3.10 sau mai nou.
    echo Descarca ultima versiune de la https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM --- Mediu virtual, ca sa nu amestecam cu restul sistemului -----------
if not exist "gamebot\.venv" (
    echo Creez mediul virtual...
    %PY% -m venv "gamebot\.venv"
    if errorlevel 1 (
        echo EROARE la crearea mediului virtual.
        pause
        exit /b 1
    )
)

echo Instalez bibliotecile necesare...
echo.
call "gamebot\.venv\Scripts\python.exe" -m pip install --upgrade pip
call "gamebot\.venv\Scripts\python.exe" -m pip install -r "gamebot\requirements.txt"
if errorlevel 1 (
    echo.
    echo EROARE la instalarea bibliotecilor. Verifica legatura la internet.
    pause
    exit /b 1
)

echo.
echo ===============================================
echo   Gata. Porneste acum bot.bat
echo ===============================================
echo.
echo IMPORTANT: da click DREAPTA pe bot.bat si alege
echo "Run as administrator" (Ruleaza ca administrator),
echo altfel tastele trimise nu ajung in joc.
echo.
pause
