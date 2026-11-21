@echo off
chcp 65001 >nul
title Marches Publics Maroc - Intelligence & Ingestion Suite
cd /d "%~dp0"

echo ======================================================================
echo   MARCHÉS PUBLICS MAROC - LANCEUR & INGESTION HORS-LIGNE
echo ======================================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas détecté dans votre variable d'environnement PATH.
    echo Veuillez installer Python 3.12+ ou l'ajouter à votre PATH.
    echo.
    pause
    exit /b 1
)

python scripts\launcher.py %*
if %errorlevel% neq 0 (
    echo.
    echo Le programme s'est arrêté avec le code %errorlevel%.
    pause
)
