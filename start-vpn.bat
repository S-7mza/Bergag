@echo off
title Bergag VPN & SSH Tunnel
color 0A
cls
echo ===============================================================================
echo   🚀 Bergag Instant SSH Tunnel & Local Gateway
echo   Jump Host: manager@41.214.254.0 (Authenticated via your SSH Key)
echo ===============================================================================
echo.
echo   [ACTIVE LOCAL PORTS]
echo   1. SSH to Server    : 127.0.0.1:22 and 127.0.0.1:2222 (^---> 192.168.1.3:22)
echo   2. Web App          : http://localhost:8000            (^---> 192.168.1.3:8000)
echo   3. SOCKS5 Proxy     : 127.0.0.1:1080  (Full access to 192.168.1.* network)
echo   4. OPNsense WebGUI  : https://localhost:9443           (^---> 192.168.1.1:9443)
echo.
echo   * SSH Connection Options (Port 22 Standard):
echo     - Terminal : ssh 192.168.1.3   OR   ssh 127.0.0.1
echo     - Termius  : Host 127.0.0.1, Port 22, User: manager, Pass: 123
echo     - PuTTY    : Host 127.0.0.1, Port 22, User: manager, Pass: 123
echo     - Or run   : ssh-server.bat
echo.
echo   Keep this window open while working. Press Ctrl+C to stop.
echo ===============================================================================
echo.
ssh -D 1080 -L 22:192.168.1.3:22 -L 2222:192.168.1.3:22 -L 8000:192.168.1.3:8000 -L 9443:192.168.1.1:9443 -N -C jumphost-prod
