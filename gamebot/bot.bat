@echo off
setlocal enabledelayedexpansion
title gamebot
cd /d "%~dp0.."

set PYEXE=gamebot\.venv\Scripts\python.exe
if not exist "%PYEXE%" (
    echo Nu gasesc mediul virtual. Ruleaza intai instalare.bat
    echo.
    pause
    exit /b 1
)

set PROFIL=gamebot\profiles\drakensang.yaml

:meniu
cls
echo ===============================================
echo   gamebot
echo ===============================================
echo   Profil: %PROFIL%
echo.
echo   PREGATIRE
echo     1. Verifica ce vede botul pe ecran
echo     2. Calibreaza o regiune (minimap, bara de viata)
echo     3. Calibreaza o culoare (viata, mob-uri)
echo.
echo   INVATARE
echo     4. Inregistreaza o ruta (mergi tu traseul)
echo     5. Invata abilitatile din luptele inregistrate
echo.
echo   RULARE
echo     6. Porneste in gol (proba, nu trimite input)
echo     7. Porneste botul
echo.
echo     8. Vezi rutele inregistrate
echo     9. Schimba profilul
echo     0. Iesire
echo.
set /p optiune="Alege: "

if "%optiune%"=="1" goto check
if "%optiune%"=="2" goto regiune
if "%optiune%"=="3" goto culoare
if "%optiune%"=="4" goto inregistrare
if "%optiune%"=="5" goto invata
if "%optiune%"=="6" goto proba
if "%optiune%"=="7" goto ruleaza
if "%optiune%"=="8" goto rute
if "%optiune%"=="9" goto profil
if "%optiune%"=="0" exit /b 0
goto meniu

:check
"%PYEXE%" -m gamebot.main check --profile "%PROFIL%"
pause
goto meniu

:regiune
echo.
echo Nume uzuale: minimap, health_bar, target_health_bar, cast_bar
set /p nume="Ce regiune calibrezi: "
"%PYEXE%" -m gamebot.main calibrate region --name "%nume%" --profile "%PROFIL%"
pause
goto meniu

:culoare
echo.
echo Nume uzuale: health, enemy_nameplate
set /p nume="Ce culoare calibrezi: "
"%PYEXE%" -m gamebot.main calibrate color --name "%nume%" --profile "%PROFIL%"
pause
goto meniu

:inregistrare
echo.
set /p ruta="Nume pentru ruta noua (ex: padure1): "
echo.
echo In joc: F4=portal  F5=drum  F6=zona de lupta  F8=vendor
echo         F9=pauza   F10=stop si salveaza
echo.
"%PYEXE%" -m gamebot.main record --profile "%PROFIL%" --name "%ruta%"
pause
goto meniu

:invata
echo.
set /p ruta="Din ce ruta invata (numele folosit la inregistrare): "
"%PYEXE%" -m gamebot.main learn --profile "%PROFIL%" --route "gamebot\routes\%ruta%"
pause
goto meniu

:proba
echo.
set /p ruta="Ce ruta rulezi: "
"%PYEXE%" -m gamebot.main run --profile "%PROFIL%" --route "gamebot\routes\%ruta%" --dry-run
pause
goto meniu

:ruleaza
echo.
set /p ruta="Ce ruta rulezi: "
set /p minute="Cate minute (Enter = cat scrie in profil): "
echo.
echo F12 = oprire imediata    F11 = pauza
echo.
if "%minute%"=="" (
    "%PYEXE%" -m gamebot.main run --profile "%PROFIL%" --route "gamebot\routes\%ruta%"
) else (
    "%PYEXE%" -m gamebot.main run --profile "%PROFIL%" --route "gamebot\routes\%ruta%" --max-minutes %minute%
)
pause
goto meniu

:rute
"%PYEXE%" -m gamebot.main routes
pause
goto meniu

:profil
echo.
echo Fisierele din gamebot\profiles:
dir /b "gamebot\profiles\*.yaml"
echo.
set /p nume="Numele fisierului (fara cale): "
set PROFIL=gamebot\profiles\%nume%
goto meniu
