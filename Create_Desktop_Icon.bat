@echo off
chcp 65001 >nul
title Installation de l'Icône de Bureau - Marchés Publics Maroc
cd /d "%~dp0"

echo Création du raccourci avec icône sur votre Bureau Windows...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_desktop_shortcut.ps1"

echo.
echo Vous pouvez maintenant double-cliquer sur l'icône "Marches Publics Maroc" sur votre Bureau !
echo.
pause
