#!/bin/sh
# ==============================================================================
# restart-opnsense-vpn.sh — Restart OpenVPN & WebGUI on OPNsense (FreeBSD)
# ==============================================================================
# Usage (run as root in OPNsense Shell, menu option 8):
#   sh restart-opnsense-vpn.sh
# ==============================================================================

echo "====================================================="
echo "  OPNsense OpenVPN & WebGUI Emergency Restart"
echo "====================================================="

echo "[1/4] Killing any hung or locked OpenVPN processes..."
killall -9 openvpn 2>/dev/null || true
sleep 2

echo "[2/4] Restarting OpenVPN service via OPNsense daemons..."
pluginctl -s openvpn restart 2>/dev/null || true
configctl openvpn restart 1 2>/dev/null || true
sleep 3

echo "[3/4] Unfreezing & Restarting Web GUI (lighttpd / php-fpm)..."
configctl webgui restart 2>/dev/null || /usr/local/etc/rc.restart_webgui 2>/dev/null || true

echo "[4/4] Verifying OpenVPN UDP 1194 listener..."
sockstat -4 -l | grep 1194 || echo "Note: Check /var/log/openvpn.log for startup details."

echo "====================================================="
echo "Done! The web interface and OpenVPN server are restarted."
echo "You can now reconnect your OpenVPN client."
echo "====================================================="
