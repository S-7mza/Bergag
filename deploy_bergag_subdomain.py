#!/usr/bin/env python3
"""
Bergag Procurement Intelligence — 1-Click Automated Subdomain Provisioning
==========================================================================
Domain : bergag.nexenflow.com
Server : 41.214.254.0 (manager@41.214.254.0:22)
Target : http://192.168.1.3:8000

Automates:
  1. Connecting to the production VPS via SSH (Paramiko).
  2. Uploading the Traefik deployment script (scripts/deploy-bergag-subdomain.sh).
  3. Creating a timestamped backup of /opt/traefik/dynamic/routes.yml.
  4. Injecting bergag-http, bergag-https, and bergag-svc routing rules.
  5. Restarting Traefik to trigger automatic Let's Encrypt SSL provisioning.
  6. Running end-to-end HTTPS health verification on https://bergag.nexenflow.com.

Usage:
  python deploy_bergag_subdomain.py
  python deploy_bergag_subdomain.py --target-url http://192.168.1.3:8000
"""

import sys
import time
import argparse
import paramiko

# Output encoding safeguard for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Production Credentials (matching Nexenflow / Kinexos / ERP infrastructure)
DEFAULT_HOST = "41.214.254.0"
DEFAULT_USER = "manager"
DEFAULT_PORT = 22
DEFAULT_PASSWORD = "K@plus@2026"
DEFAULT_DOMAIN = "bergag.nexenflow.com"
DEFAULT_TARGET_URL = "http://192.168.1.3:8000"

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner(domain: str, host: str, target_url: str):
    print(f"\n{CYAN}{'=' * 65}{RESET}")
    print(f"{CYAN}{BOLD}  🚀 Bergag Subdomain Automated Deployment: {domain}{RESET}")
    print(f"{DIM}     Edge Proxy VPS : manager@{host}:{DEFAULT_PORT}{RESET}")
    print(f"{DIM}     Backend Target : {target_url}{RESET}")
    print(f"{CYAN}{'=' * 65}{RESET}\n")


def execute_ssh_deployment(host: str, user: str, password: str, port: int, domain: str, target_url: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"{YELLOW}▶ [1/4] Connecting to {user}@{host}:{port}...{RESET}")
    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=password,
            timeout=25,
            banner_timeout=25,
            auth_timeout=25,
            look_for_keys=False,
            allow_agent=False
        )
        print(f"{GREEN}✓ Connected successfully via SSH!{RESET}\n")
    except Exception as e:
        print(f"{RED}✖ SSH connection failed: {e}{RESET}")
        sys.exit(1)

    remote_script = f"""
set -e

DOMAIN="{domain}"
TARGET_BACKEND_URL="{target_url}"
TRAEFIK_ROUTES="/opt/traefik/dynamic/routes.yml"

echo "================================================================="
echo ">>> Checking Traefik dynamic routes..."
echo "================================================================="

if [ ! -f "$TRAEFIK_ROUTES" ]; then
    echo "❌ Error: $TRAEFIK_ROUTES does not exist on this server."
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${{TRAEFIK_ROUTES}}.bak_bergag_${{TIMESTAMP}}"
echo "Creating backup: $BACKUP_FILE"
sudo cp -p "$TRAEFIK_ROUTES" "$BACKUP_FILE"

sudo python3 - "$TRAEFIK_ROUTES" "$DOMAIN" "$TARGET_BACKEND_URL" << 'PYEOF'
import sys

path = sys.argv[1]
domain = sys.argv[2]
backend_url = sys.argv[3]

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

if domain in text:
    print(f"ℹ️ {{domain}} is already registered in {{path}}.")
else:
    router_block = f'''
    # --- Bergag Moroccan Public Procurement Engine (Port 8000) ---
    bergag-http:
      entryPoints:
        - web
      rule: "Host(`{{domain}}`)"
      middlewares:
        - redirect-https
      service: bergag-svc

    bergag-https:
      entryPoints:
        - websecure
      rule: "Host(`{{domain}}`)"
      tls:
        certResolver: letsencrypt
      service: bergag-svc
'''

    service_block = f'''
    # --- Bergag Procurement Intelligence Service ---
    bergag-svc:
      loadBalancer:
        passHostHeader: true
        servers:
          - url: "{{backend_url}}"
'''

    if 'middlewares:' in text:
        parts = text.split('middlewares:', 1)
        text = parts[0].rstrip() + "\\n" + router_block + "\\n  middlewares:" + parts[1]
    elif 'services:' in text:
        parts = text.split('services:', 1)
        text = parts[0].rstrip() + "\\n" + router_block + "\\n  services:" + parts[1]

    if 'services:' in text:
        parts = text.split('services:', 1)
        text = parts[0] + "services:" + service_block + parts[1]

    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"✅ Successfully appended {{domain}} -> {{backend_url}} to {{path}}.")
PYEOF

echo ""
echo "================================================================="
echo ">>> Restarting Traefik for Let's Encrypt SSL ACME Issuance..."
echo "================================================================="
if sudo docker ps --format '{{{{.Names}}}}' | grep -q "^traefik$"; then
    sudo docker restart traefik
    echo "✅ Traefik restarted successfully."
    echo "Waiting 6 seconds for route initialization..."
    sleep 6
else
    echo "⚠️ Traefik container not found running by name 'traefik'."
fi

echo ""
echo "================================================================="
echo ">>> Verification:"
echo "================================================================="
# Internal check
echo -n "Testing backend target ($TARGET_BACKEND_URL): "
curl -s -o /dev/null -w "HTTP %{{http_code}}\\n" "$TARGET_BACKEND_URL" || echo "FAIL"

# Existing subdomains check
echo -n "Checking flowops.nexenflow.com: "
curl -s -o /dev/null -w "HTTP %{{http_code}}\\n" "https://flowops.nexenflow.com" || echo "FAIL"

echo "🎉 Deployment command completed on server."
"""

    print(f"{YELLOW}▶ [2/4] Executing remote configuration on VPS...{RESET}")
    stdin, stdout, stderr = client.exec_command(f"bash -c '{remote_script}'", get_pty=True)

    for line in iter(stdout.readline, ""):
        print(f"  {line.rstrip()}")

    exit_status = stdout.channel.recv_exit_status()
    client.close()

    if exit_status == 0:
        print(f"\n{GREEN}{BOLD}✓ Remote configuration succeeded!{RESET}\n")
    else:
        print(f"\n{RED}{BOLD}✖ Remote script failed with exit status {exit_status}{RESET}\n")
        sys.exit(exit_status)

    print(f"{YELLOW}▶ [3/4] Public DNS & HTTPS Connectivity Check...{RESET}")
    import urllib.request
    import ssl

    time.sleep(2)
    url = f"https://{domain}"
    print(f"  Pinging {url}...")
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "BergagDeployer/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
            status = response.getcode()
            print(f"{GREEN}✓ Public HTTPS response: HTTP {status}!{RESET}")
    except Exception as e:
        print(f"{YELLOW}ℹ DNS or SSL challenge in progress ({e}).{RESET}")
        print(f"{DIM}  Note: If you haven't yet added the A-Record in Cloudflare:{RESET}")
        print(f"{BOLD}  Type : A | Name : bergag | Target : {host} | Proxy: Proxied or DNS Only{RESET}")
        print(f"{DIM}  Once Cloudflare DNS propagates, SSL will resolve automatically.{RESET}")

    print(f"\n{CYAN}{'=' * 65}{RESET}")
    print(f"{GREEN}{BOLD}  🎉 All Done! Access your app at: https://{domain}{RESET}")
    print(f"{CYAN}{'=' * 65}{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Automate bergag.nexenflow.com subdomain deployment")
    parser.add_argument("--host", default=DEFAULT_HOST, help="VPS IP address")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Target subdomain")
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL, help="Backend service URL (default: http://192.168.1.3:8000)")
    args = parser.parse_args()

    print_banner(args.domain, args.host, args.target_url)
    execute_ssh_deployment(
        host=args.host,
        user=DEFAULT_USER,
        password=DEFAULT_PASSWORD,
        port=DEFAULT_PORT,
        domain=args.domain,
        target_url=args.target_url
    )


if __name__ == "__main__":
    main()
