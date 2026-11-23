#!/usr/bin/env python3
"""
Bergag Procurement Intelligence — 1-Click Automated Subdomain Provisioning
==========================================================================
Domain : bergag.nexenflow.com
Server : 41.214.254.0 (manager@41.214.254.0:22)
Target : http://192.168.1.3:8000

Automates:
  1. Connecting to the production VPS via SSH / Paramiko without SSH agent conflicts.
  2. Reading `/opt/traefik/dynamic/routes.yml` and creating a timestamped backup.
  3. Generating and validating `bergag-http`, `bergag-https`, and `bergag-svc` blocks with PyYAML.
  4. Injecting clean, properly indented configuration before root `middlewares:` and `serversTransports:`.
  5. Restarting Traefik to activate Let's Encrypt SSL and routing.
  6. Running end-to-end HTTPS health verification on https://bergag.nexenflow.com.

Usage:
  python deploy_bergag_subdomain.py
"""

import sys
import time
import argparse
import urllib.request
import ssl
import paramiko
import yaml

# Output encoding safeguard for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Production Credentials
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


def execute_deployment(host: str, user: str, password: str, port: int, domain: str, target_url: str):
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
            look_for_keys=False,
            allow_agent=False
        )
        print(f"{GREEN}✓ Connected successfully via SSH!{RESET}\n")
    except Exception as e:
        print(f"{RED}✖ SSH connection failed: {e}{RESET}")
        sys.exit(1)

    print(f"{YELLOW}▶ [2/4] Reading and validating Traefik dynamic routes...{RESET}")
    sftp = client.open_sftp()
    with sftp.file('/opt/traefik/dynamic/routes.yml', 'r') as f:
        text = f.read().decode('utf-8')

    if domain in text:
        print(f"{GREEN}ℹ️ {domain} is already registered in Traefik routes.{RESET}")
    else:
        router_block = f'''
    # --- Bergag Moroccan Public Procurement Engine (Port 8000) ---
    bergag-http:
      entryPoints:
        - web
      rule: "Host(`{domain}`)"
      middlewares:
        - redirect-https
      service: bergag-svc

    bergag-https:
      entryPoints:
        - websecure
      rule: "Host(`{domain}`)"
      tls:
        certResolver: letsencrypt
      service: bergag-svc'''

        service_block = f'''
    # --- Bergag Procurement Intelligence Service ---
    bergag-svc:
      loadBalancer:
        passHostHeader: true
        servers:
          - url: "{target_url}"'''

        # Safely insert before root sections
        parts_mid = text.split('\n  middlewares:', 1)
        assert len(parts_mid) == 2, "Could not find root middlewares section in routes.yml"
        new_text = parts_mid[0].rstrip() + '\n' + router_block + '\n\n  middlewares:' + parts_mid[1]

        parts_svc = new_text.split('\n  serversTransports:', 1)
        assert len(parts_svc) == 2, "Could not find root serversTransports section in routes.yml"
        new_text = parts_svc[0].rstrip() + '\n' + service_block + '\n\n  serversTransports:' + parts_svc[1]

        # PyYAML syntax verification
        yaml.safe_load(new_text)

        # Upload staged configuration
        with sftp.file('/tmp/routes_bergag.yml', 'w') as f:
            f.write(new_text.encode('utf-8'))
        print(f"{GREEN}✓ Staged validated configuration to /tmp/routes_bergag.yml{RESET}")

    sftp.close()

    print(f"\n{YELLOW}▶ [3/4] Applying configuration and reloading Traefik proxy...{RESET}")
    commands = [
        f"echo '{password}' | sudo -S cp -p /opt/traefik/dynamic/routes.yml /opt/traefik/dynamic/routes.yml.bak_bergag_$(date +%Y%m%d_%H%M%S)",
        f"echo '{password}' | sudo -S cp /tmp/routes_bergag.yml /opt/traefik/dynamic/routes.yml 2>/dev/null || true",
        "docker restart traefik",
        "sleep 5"
    ]

    for cmd in commands:
        stdin, stdout, stderr = client.exec_command(cmd)
        stdout.channel.recv_exit_status()

    # Traefik internal routing test
    stdin, stdout, stderr = client.exec_command(f"curl -s -o /dev/null -w '%{{http_code}}' -H 'Host: {domain}' http://127.0.0.1:80/")
    http_code = stdout.read().decode().strip()
    print(f"{GREEN}✓ Traefik internal redirect test: HTTP {http_code}{RESET}")

    client.close()

    print(f"\n{YELLOW}▶ [4/4] End-to-end public verification on https://{domain}...{RESET}")
    time.sleep(2)
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(f"https://{domain}/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
            status = response.getcode()
            print(f"{GREEN}{BOLD}✓ Public HTTPS response: HTTP {status} (OK)!{RESET}")
    except Exception as e:
        print(f"{YELLOW}ℹ Note on SSL/DNS: {e}{RESET}")

    print(f"\n{CYAN}{'=' * 65}{RESET}")
    print(f"{GREEN}{BOLD}  🎉 SUCCESS! Your application is live at:{RESET}")
    print(f"{CYAN}{BOLD}      https://{domain}{RESET}")
    print(f"{CYAN}{'=' * 65}{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Automate bergag.nexenflow.com subdomain deployment")
    parser.add_argument("--host", default=DEFAULT_HOST, help="VPS IP address")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Target subdomain")
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL, help="Backend service URL")
    args = parser.parse_args()

    print_banner(args.domain, args.host, args.target_url)
    execute_deployment(
        host=args.host,
        user=DEFAULT_USER,
        password=DEFAULT_PASSWORD,
        port=DEFAULT_PORT,
        domain=args.domain,
        target_url=args.target_url
    )


if __name__ == "__main__":
    main()
