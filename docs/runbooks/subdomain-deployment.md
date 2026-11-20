# Production Subdomain Deployment Runbook — `bergag.nexenflow.com`

> **Domain:** `https://bergag.nexenflow.com`  
> **Target Service:** Bergag Moroccan Public Procurement Intelligence (`http://192.168.1.3:8000`)  
> **Edge Proxy:** Traefik on VPS (`41.214.254.0`) with Let's Encrypt ACME SSL  
> **Dynamic Routes Config:** `/opt/traefik/dynamic/routes.yml`

---

## 1. Architecture Map

```
                     https://bergag.nexenflow.com
                                   │
                                   ▼
             ┌───────────────────────────────────────────┐
             │       Cloudflare DNS (nexenflow.com)      │
             │   A-Record: bergag -> 41.214.254.0        │
             └─────────────────────┬─────────────────────┘
                                   │
                                   ▼
             ┌───────────────────────────────────────────┐
             │     EDGE REVERSE PROXY (Traefik on VPS)   │
             │  File Provider: /opt/traefik/dynamic/     │
             │                 routes.yml                │
             │  SSL: Let's Encrypt (websecure / 443)     │
             └─────────────────────┬─────────────────────┘
                                   │
                                   ▼
             ┌───────────────────────────────────────────┐
             │   Bergag Procurement Intelligence App     │
             │       FastAPI / Uvicorn Server            │
             │         http://192.168.1.3:8000           │
             └───────────────────────────────────────────┘
```

---

## 2. Step 1: Cloudflare DNS Setup

In your Cloudflare dashboard under `nexenflow.com`:
1. Go to **DNS** > **Records**.
2. Click **Add Record**:
   - **Type:** `A`
   - **Name:** `bergag` (which forms `bergag.nexenflow.com`)
   - **IPv4 address:** `41.214.254.0`
   - **Proxy status:** Proxied (🟠) or DNS Only (☁️)
   - **TTL:** Auto
3. Save record.

---

## 3. Step 2: One-Click Execution

You have two ready-to-run options matching the architecture in your other projects (`interventions`, `Kinexos`, `nexenflow`):

### Option A: From your Local Machine (1-Click Python via SSH)

Execute directly from the repository root:
```powershell
python deploy_bergag_subdomain.py
```
*Connects over SSH to `41.214.254.0`, backs up Traefik dynamic routes, configures the `bergag-http` and `bergag-https` routers + `bergag-svc` (pointing to `http://192.168.1.3:8000`), restarts Traefik to issue the SSL certificate, and verifies `https://bergag.nexenflow.com`.*

---

### Option B: Directly on the VPS (Bash Script)

```bash
# Upload and run on VPS
scp scripts/deploy-bergag-subdomain.sh manager@41.214.254.0:/home/manager/
ssh manager@41.214.254.0
bash /home/manager/deploy-bergag-subdomain.sh
```

---

## 4. Verification & Health Checks

```bash
# 1. Internal backend reachability (from server)
curl -I http://192.168.1.3:8000/api/crawler/status

# 2. Public HTTPS endpoint (Let's Encrypt SSL)
curl -Is https://bergag.nexenflow.com | head -1
```

---

## 5. Rollback Procedure

If you ever need to restore the Traefik configuration to the exact state before the deployment:
```bash
sudo cp $(ls -t /opt/traefik/dynamic/routes.yml.bak_bergag_* | head -1) /opt/traefik/dynamic/routes.yml
sudo docker restart traefik
```
