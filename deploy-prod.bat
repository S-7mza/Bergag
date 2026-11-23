@echo off
title Deploy & Update Bergag Production
color 0E
cls
echo ===============================================================================
echo   🚀 1-Click Update & Deploy: Bergag Production Server (192.168.1.3)
echo ===============================================================================
echo.
echo Running remote git pull and container restart in /opt/bergag...
echo.

ssh 192.168.1.3 "cd /opt/bergag && echo '▶ Pulling latest commits from GitHub...' && git pull origin main && echo '▶ Rebuilding & restarting web container...' && docker compose up -d --build && docker compose restart web && echo '▶ Container status:' && docker compose ps"

echo.
echo ===============================================================================
echo ✓ Deployment completed! Check status at https://bergag.nexenflow.com
echo ===============================================================================
echo.
pause
