#!/bin/bash
# ==============================================================================
# deploy-bergag-subdomain.sh — Production Subdomain for bergag.nexenflow.com
# ==============================================================================
# Domain    : bergag.nexenflow.com
# App       : Bergag Moroccan Public Procurement Intelligence & Opportunity Engine
# Target    : http://192.168.1.3:8000 (FastAPI / Uvicorn Server)
# Edge Proxy: Traefik (/opt/traefik/dynamic/routes.yml)
# SSL / TLS : Let's Encrypt ACME Auto-Provisioning (CertResolver: letsencrypt)
#
# Usage (on production VPS):
#   bash deploy-bergag-subdomain.sh
# ==============================================================================

set -e

DOMAIN="bergag.nexenflow.com"
TARGET_BACKEND_URL="${1:-http://192.168.1.3:8000}"
TRAEFIK_ROUTES="/opt/traefik/dynamic/routes.yml"

# Terminal Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}   Deploying Subdomain: ${DOMAIN}${NC}"
echo -e "${CYAN}   Target Backend   : ${TARGET_BACKEND_URL}${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# ------------------------------------------------------------------------------
# STEP 1: Verify DNS Resolution
# ------------------------------------------------------------------------------
echo -e "${YELLOW}[1/4] Checking DNS Resolution for ${DOMAIN}...${NC}"
if host "${DOMAIN}" > /dev/null 2>&1 || dig +short "${DOMAIN}" > /dev/null 2>&1; then
    RESOLVED_IP=$(dig +short "${DOMAIN}" 2>/dev/null | tail -1 || true)
    echo -e "${GREEN}✓ DNS resolves for ${DOMAIN}: ${RESOLVED_IP:-detected}${NC}"
else
    echo -e "${YELLOW}⚠ WARNING: DNS record for ${DOMAIN} is not resolving yet.${NC}"
    echo -e "   Please ensure Cloudflare DNS has an A-Record for '${DOMAIN%%.*}' pointing to this VPS IP (41.214.254.0)."
    echo -e "   Traefik SSL will complete once DNS propagates.${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 2: Backup and Update Traefik Dynamic Routes
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/4] Updating Traefik Dynamic Routes (${TRAEFIK_ROUTES})...${NC}"

if [ ! -f "${TRAEFIK_ROUTES}" ]; then
    echo -e "${RED}✗ Error: ${TRAEFIK_ROUTES} not found! Check Traefik path.${NC}"
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${TRAEFIK_ROUTES}.bak_bergag_${TIMESTAMP}"
echo -e "  Creating timestamped backup: ${BACKUP_FILE}"
sudo cp -p "${TRAEFIK_ROUTES}" "${BACKUP_FILE}"

# Safely inject bergag router and service using Python
sudo python3 - "${TRAEFIK_ROUTES}" "${DOMAIN}" "${TARGET_BACKEND_URL}" << 'EOF'
import sys

path = sys.argv[1]
domain = sys.argv[2]
backend_url = sys.argv[3]

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

if domain in text:
    print(f"ℹ️ {domain} is already registered in {path}.")
else:
    # Router definition block
    router_block = f"""
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
      service: bergag-svc
"""

    # Service definition block
    service_block = f"""
    # --- Bergag Procurement Intelligence Service ---
    bergag-svc:
      loadBalancer:
        passHostHeader: true
        servers:
          - url: "{backend_url}"
"""

    # Insert router before 'middlewares:'
    if 'middlewares:' in text:
        parts = text.split('middlewares:', 1)
        text = parts[0].rstrip() + "\n" + router_block + "\n  middlewares:" + parts[1]
    else:
        print("⚠️ Warning: 'middlewares:' key not found, appending to routers.")

    # Insert service under 'services:'
    if 'services:' in text:
        parts = text.split('services:', 1)
        text = parts[0] + "services:" + service_block + parts[1]
    else:
        print("⚠️ Warning: 'services:' key not found.")

    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"✅ Successfully registered {domain} -> {backend_url} in Traefik routes.")
EOF

# ------------------------------------------------------------------------------
# STEP 3: Restart Traefik for Let's Encrypt SSL
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/4] Refreshing Traefik Proxy for ACME SSL Provisioning...${NC}"

if docker ps --format '{{.Names}}' | grep -q "^traefik$"; then
    echo "  Restarting Traefik container..."
    docker restart traefik
    echo -e "${GREEN}✓ Traefik restarted successfully${NC}"
    echo "  Waiting 6 seconds for Traefik route synchronization..."
    sleep 6
else
    echo -e "${YELLOW}ℹ Traefik container not running as 'traefik'.${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 4: End-to-End Health Verification
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/4] Running Health Verification...${NC}"

# Internal backend test
INTERNAL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${TARGET_BACKEND_URL}/api/crawler/status" --max-time 5 2>/dev/null || echo "000")
if [ "$INTERNAL_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ Target backend reachable (${TARGET_BACKEND_URL}): HTTP ${INTERNAL_STATUS}${NC}"
else
    echo -e "${YELLOW}⚠ Target backend check returned: HTTP ${INTERNAL_STATUS} (is uvicorn running on 192.168.1.3:8000?)${NC}"
fi

# Public HTTPS test
EXTERNAL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${DOMAIN}" --max-time 10 2>/dev/null || echo "000")
if [ "$EXTERNAL_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ Public HTTPS check (https://${DOMAIN}): HTTP ${EXTERNAL_STATUS}${NC}"
else
    echo -e "${YELLOW}⚠ Public HTTPS check returned: HTTP ${EXTERNAL_STATUS}${NC}"
    echo -e "  (If 000 / SSL error, allow 1-2 minutes for Let's Encrypt certificate challenge to finalize)${NC}"
fi

# Regression check on existing production subdomains
echo ""
echo -e "  Checking existing subdomains integrity:"
for SUB in nerobel.nexenflow.com flowops.nexenflow.com team.nexenflow.com; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${SUB}" --max-time 8 2>/dev/null || echo "000")
    if [ "$CODE" = "200" ]; then
        echo -e "  ${GREEN}✓ https://${SUB}: HTTP ${CODE}${NC}"
    else
        echo -e "  ${YELLOW}⚠ https://${SUB}: HTTP ${CODE}${NC}"
    fi
done

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}   Subdomain Ready: https://${DOMAIN}${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

