@echo off
setlocal enabledelayedexpansion
title Bergag Procurement - Production Remote Manager
color 0B

:: ==============================================================================
:: Bergag Moroccan Public Procurement Engine — Remote Ops & Tunnel Manager
:: ==============================================================================
:: Jump Host VPS : 41.214.254.0 (manager:K@plus@2026)
:: Target Server : 192.168.1.3 (FastAPI Uvicorn port 8000 / SSH port 22)
:: Router / VPN  : 192.168.1.1 (OPNsense WebGUI port 9443)
:: ==============================================================================

set JUMP_HOST=41.214.254.0
set JUMP_PORT=22
set JUMP_USER=manager
set TARGET_IP=192.168.1.3
set TARGET_USER=manager
set TARGET_PORT=22
set OPN_IP=192.168.1.1
set OPN_PORT=9443

if not "%1"=="" (
    set CHOICE=%1
    goto HANDLE_CHOICE
)

:MENU
cls
echo ===============================================================================
echo        BERGAG PROCUREMENT INTELLIGENCE - PRODUCTION OPS MANAGER
echo ===============================================================================
echo   Jump Host  : %JUMP_USER%@%JUMP_HOST%:%JUMP_PORT%  (Edge Proxy VPS)
echo   Target App : %TARGET_IP%:8000  (Live: https://bergag.nexenflow.com)
echo   Router/VPN : %OPN_IP%:%OPN_PORT%  (OPNsense Firewall)
echo ===============================================================================
echo.
echo   [1] 🚀 1-Click Remote Deploy (git pull + docker rebuild on 192.168.1.3)
echo   [2] 💻 SSH Terminal into Target Server (192.168.1.3 via JumpHost)
echo   [3] 🖥️  SSH Terminal into Jump Host VPS (41.214.254.0)
echo   [4] 🌐 Start SOCKS5 SSH VPN Proxy (127.0.0.1:1080 - Bypasses OpenVPN)
echo   [5] 🔌 Port-Forward App + OPNsense (localhost:8000 and localhost:9443)
echo   [6] 📋 View OPNsense SSH Recovery Guide (Restart OpenVPN & WebGUI)
echo   [7] 🔍 Check Production Health (https://bergag.nexenflow.com)
echo   [8] ❌ Exit
echo.
echo ===============================================================================
set /p CHOICE="Select an option [1-8]: "

:HANDLE_CHOICE
if "%CHOICE%"=="1" goto DEPLOY
if "%CHOICE%"=="2" goto SSH_TARGET
if "%CHOICE%"=="3" goto SSH_JUMP
if "%CHOICE%"=="4" goto SOCKS5
if "%CHOICE%"=="5" goto FORWARD
if "%CHOICE%"=="6" goto OPN_RESCUE
if "%CHOICE%"=="7" goto HEALTH
if "%CHOICE%"=="8" goto EXIT

echo Invalid selection. Please choose 1-8.
timeout /t 2 >nul
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 1: 1-Click Remote Deploy
:: ------------------------------------------------------------------------------
:DEPLOY
cls
echo ===============================================================================
echo   [1/1] Launching Automated Remote Deployment via Python / JumpHost
echo ===============================================================================
echo.
python scripts\remote_deploy.py
echo.
echo Press any key to return to menu...
pause >nul
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 2: SSH Terminal into Target Server (192.168.1.3 via JumpHost)
:: ------------------------------------------------------------------------------
:SSH_TARGET
cls
echo ===============================================================================
echo   Connecting to Target Server (%TARGET_IP%) via JumpHost (%JUMP_HOST%)...
echo ===============================================================================
echo.
echo Note: When prompted for password:
echo   - Jump host (%JUMP_HOST%) password is: K@plus@2026
echo   - Target host (%TARGET_IP%) password: enter your server password
echo.
set /p TUSER="Enter target username [%TARGET_USER%]: "
if "%TUSER%"=="" set TUSER=%TARGET_USER%

echo Connecting: ssh -J %JUMP_USER%@%JUMP_HOST%:%JUMP_PORT% %TUSER%@%TARGET_IP% ...
ssh -J %JUMP_USER%@%JUMP_HOST%:%JUMP_PORT% %TUSER%@%TARGET_IP%
echo.
echo Disconnected from target server.
pause
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 3: SSH Terminal into Jump Host (41.214.254.0)
:: ------------------------------------------------------------------------------
:SSH_JUMP
cls
echo ===============================================================================
echo   Connecting to Jump Host VPS (%JUMP_HOST%)...
echo ===============================================================================
echo.
echo Password is: K@plus@2026
echo.
ssh %JUMP_USER%@%JUMP_HOST% -p %JUMP_PORT%
echo.
echo Disconnected from jump host.
pause
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 4: SOCKS5 SSH VPN Proxy (127.0.0.1:1080)
:: ------------------------------------------------------------------------------
:SOCKS5
cls
echo ===============================================================================
echo   🌐 Starting SOCKS5 Dynamic SSH VPN Tunnel on port 1080
echo ===============================================================================
echo.
echo   This replaces OpenVPN completely!
echo   When connected:
echo     - Configure your Browser or system proxy to SOCKS5: 127.0.0.1:1080
echo     - You will be able to browse:
echo         * OPNsense WebGUI : https://192.168.1.1:9443
echo         * Bergag App      : http://192.168.1.3:8000
echo         * Any internal 192.168.1.* host
echo.
echo Password for %JUMP_USER%@%JUMP_HOST% is: K@plus@2026
echo Press Ctrl+C at any time to stop the VPN proxy.
echo.
ssh -D 1080 -N -C %JUMP_USER%@%JUMP_HOST% -p %JUMP_PORT%
echo.
echo Proxy stopped.
pause
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 5: Port-Forward Localhost (8000 & 9443)
:: ------------------------------------------------------------------------------
:FORWARD
cls
echo ===============================================================================
echo   🔌 Starting Local Port Forwarding:
echo   - http://localhost:8000  ^---> 192.168.1.3:8000 (Bergag App)
echo   - https://localhost:9443 ^---> 192.168.1.1:9443 (OPNsense WebGUI)
echo ===============================================================================
echo.
echo Password for %JUMP_USER%@%JUMP_HOST% is: K@plus@2026
echo Keep this window open. Once connected, open:
echo    http://localhost:8000
echo    https://localhost:9443
echo.
echo Press Ctrl+C at any time to terminate port forwarding.
echo.
ssh -L 8000:192.168.1.3:8000 -L 9443:192.168.1.1:9443 -N %JUMP_USER%@%JUMP_HOST% -p %JUMP_PORT%
echo.
echo Port forwarding stopped.
pause
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 6: OPNsense SSH Recovery Guide
:: ------------------------------------------------------------------------------
:OPN_RESCUE
cls
echo ===============================================================================
echo   📋 OPNsense SSH Recovery Guide (OpenVPN & Web GUI)
echo ===============================================================================
echo.
echo When the OPNsense Web Interface hangs or OpenVPN shows "Status: failed":
echo.
echo 1. Connect via SSH to OPNsense (or use Hypervisor console / Shell):
echo    ssh root@192.168.1.1
echo.
echo 2. From the OPNsense Console Menu:
echo    - Type '11' and press Enter to instantly RESTART THE WEB GUI (lighttpd/php).
echo    - Type '8' to enter the root Shell.
echo.
echo 3. In the Shell, run these exact commands to fix OpenVPN:
echo    --------------------------------------------------------------
echo    # Kill any hung OpenVPN processes:
echo    killall -9 openvpn
echo.
echo    # Restart OpenVPN service:
echo    pluginctl -s openvpn restart
echo.
echo    # Verify OpenVPN is listening on UDP 1194:
echo    sockstat -4 -l ^| grep 1194
echo    --------------------------------------------------------------
echo.
echo A complete script is saved in: scripts\restart-opnsense-vpn.sh
echo.
echo Press any key to return to menu...
pause >nul
goto MENU

:: ------------------------------------------------------------------------------
:: OPTION 7: Health Check
:: ------------------------------------------------------------------------------
:HEALTH
cls
echo ===============================================================================
echo   🔍 Checking Production Status: https://bergag.nexenflow.com
echo ===============================================================================
echo.
curl -I -s https://bergag.nexenflow.com | findstr /i "HTTP server location"
echo.
curl -s https://bergag.nexenflow.com/api/crawler/status
echo.
echo.
echo Press any key to return to menu...
pause >nul
goto MENU

:EXIT
echo Exiting.
exit /b 0
