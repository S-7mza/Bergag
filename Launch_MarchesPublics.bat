@echo off
chcp 65001 >nul
title Marches Publics Maroc - Intelligence et Ingestion Suite
cd /d "%~dp0."

echo ======================================================================
echo   MARCHES PUBLICS MAROC - LANCEUR ET INGESTION HORS-LIGNE
echo ======================================================================
echo.

set "PYTHON_EXE="

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :run
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    goto :run
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :run
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :run
    )
)

echo [ERREUR] Python n'est pas detecte sur votre systeme.
echo Veuillez installer Python 3.12+ ou verifier votre variable d'environnement PATH.
echo.
pause
exit /b 1

:run
"%PYTHON_EXE%" "%~dp0scripts\launcher.py" %*
if %errorlevel% neq 0 (
    echo.
    echo Le programme s'est arrete avec le code %errorlevel%.
    pause
)
