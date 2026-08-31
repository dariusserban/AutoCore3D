@echo off
setlocal
title actualizare gamebot
cd /d "%~dp0.."

echo ===============================================
echo   Actualizare gamebot
echo ===============================================
echo.

REM Aplicatia scrie in profil (titlul ferestrei, setarile din tabul LUPTA),
REM iar actualizarile aduc si ele versiuni noi ale acelorasi fisiere. Fara
REM pasul asta, git se opreste de fiecare data cu "local changes would be
REM overwritten". Pastram o copie si mergem mai departe.

if not exist "gamebot\profiles\backup" mkdir "gamebot\profiles\backup"

for %%F in (gamebot\profiles\*.yaml) do (
    copy /Y "%%F" "gamebot\profiles\backup\%%~nF.yaml" >nul
)
echo Copie de siguranta a profilelor: gamebot\profiles\backup
echo.

git checkout -- gamebot/profiles/ 2>nul
git pull
if errorlevel 1 (
    echo.
    echo Actualizarea nu a reusit. Trimite textul de mai sus.
    echo.
    pause
    exit /b 1
)

echo.
echo ===============================================
echo   Gata. Poti porni bot.bat sau cules.bat
echo ===============================================
echo.
echo Daca aveai reglaje proprii in profil, le gasesti in
echo gamebot\profiles\backup si le poti pune la loc.
echo.
pause
