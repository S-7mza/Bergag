@echo off
chcp 65001 >nul
title "Installation de l'Icone de Bureau - Marches Publics Maroc"
cd /d "%~dp0"

echo Creation du raccourci avec icone sur votre Bureau Windows...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_desktop_shortcut.ps1"

echo.
echo Vous pouvez maintenant double-cliquer sur l'icone "Marches Publics Maroc" sur votre Bureau !
echo.
pause