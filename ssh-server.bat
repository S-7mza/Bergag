@echo off
title Connect to Production Server (192.168.1.3)
color 0B
cls
echo ===============================================================================
echo   💻 Connecting to Production Server (192.168.1.3)...
echo   Routed automatically via Edge JumpHost (41.214.254.0)
echo ===============================================================================
echo.
set TARGET_USER=manager
set /p TUSER="Enter username [%TARGET_USER%]: "
if "%TUSER%"=="" set TUSER=%TARGET_USER%

echo.
echo Connecting to %TUSER%@192.168.1.3...
ssh -J manager@41.214.254.0 %TUSER%@192.168.1.3
echo.
echo Session closed.
pause
