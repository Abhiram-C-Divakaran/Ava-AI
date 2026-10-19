#!/usr/bin/env bash
# ==============================================================================
# Ava AI — OCI Always Free Production Beta Deployment Automation Script
# Target: Ubuntu 22.04 / 24.04 LTS on OCI VM.Standard.A1.Flex (ARM64)
# Target Cost: $0/month (Always Free Limits)
# Target Commit SHA: 993773d5282003b592c2ee2924b97e2ceb267e96
# ==============================================================================

set -euo pipefail

EXPECTED_SHA="993773d5282003b592c2ee2924b97e2ceb267e96"
REPO_URL="https://github.com/Abhiram-C-Divakaran/Ava-AI.git"
APP_DIR="/opt/ava/app"
DATA_DIR="/opt/ava/data"
BACKUP_DIR="/opt/ava/backups"
ENV_DIR="/etc/ava"
ENV_FILE="${ENV_DIR}/ava.env"

echo "======================================================================"
echo "  Ava AI — Zero-Cost OCI Always Free Production Beta Setup"
echo "  Target Architecture: ARM64 (Ampere A1 Flex) / Ubuntu LTS"
echo "  Target Commit: $EXPECTED_SHA"
echo "======================================================================"

# Check root execution
if [[ "$EUID" -ne 0 ]]; then
   echo "[!] This script must be run as root (use sudo)."
   exit 1
fi

# Step 1: Firewall & OCI iptables Configuration (Steps 8 & 9)
echo "[1/10] Configuring system firewall & OCI networking rules..."
# OCI Ubuntu images have strict iptables rules by default in /etc/iptables/rules.v4.
# We must open 80/tcp and 443/tcp in iptables as well as UFW.
if command -v iptables >/dev/null 2>&1; then
    iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 80 -j ACCEPT
    iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 443 -j ACCEPT
    if command -v netfilter-persistent >/dev/null 2>&1; then
        netfilter-persistent save || true
    fi
fi

if command -v ufw >/dev/null 2>&1; then
    ufw allow 22/tcp comment 'SSH'
    ufw allow 80/tcp comment 'HTTP Caddy'
    ufw allow 443/tcp comment 'HTTPS Caddy'
    ufw --force enable || true
    echo "  [PASS] UFW and iptables rules configured (22, 80, 443 open; 8000 internal)."
fi

# Step 2: Install System Dependencies (Step 10)
echo "[2/10] Installing system dependencies (git, curl, ca-certificates, docker, caddy)..."
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    git \
    python3 \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https

# Install Docker if not present
if ! command -v docker >/dev/null 2>&1; then
    echo "  Installing Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
fi

# Configure Docker Log Rotation (Step 30: max 10MB, 3 files)
echo "  Configuring Docker daemon log limits..."
mkdir -p /etc/docker
cat << 'EOF' > /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

# Install Caddy (Step 22)
if ! command -v caddy >/dev/null 2>&1; then
    echo "  Installing Caddy reverse proxy..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg --yes
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
fi

# Step 3: Create Persistent Data & Backup Directories (Steps 6 & 12)
echo "[3/10] Creating persistent host directories with UID 1001 ownership..."
mkdir -p "${DATA_DIR}/uploads" "${DATA_DIR}/review_images" "${BACKUP_DIR}" "${APP_DIR}" "${ENV_DIR}"
# Ava container runs as appuser UID 1001
chown -R 1001:1001 "${DATA_DIR}"
chmod 750 "${DATA_DIR}"
chmod 700 "${BACKUP_DIR}"
chmod 700 "${ENV_DIR}"
echo "  [PASS] Host persistent paths created:"
echo "         Data:    ${DATA_DIR} (owner 1001:1001, mode 750)"
echo "         Backups: ${BACKUP_DIR} (mode 700)"

# Step 4: Clone / Fetch Repository (Step 11)
echo "[4/10] Cloning Ava AI repository at exact commit ${EXPECTED_SHA}..."
if [ ! -d "${APP_DIR}/.git" ]; then
    git clone "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"
git fetch origin main
git checkout main
CURRENT_SHA=$(git rev-parse HEAD)

if [ "${CURRENT_SHA}" != "${EXPECTED_SHA}" ]; then
    echo "[!] Notice: Local SHA is ${CURRENT_SHA}, checking out verified SHA ${EXPECTED_SHA}..."
    git checkout "${EXPECTED_SHA}"
fi
echo "  [PASS] Repository active at SHA: $(git rev-parse HEAD)"

# Step 5: Production Environment File Configuration (Steps 13, 14, 15, 16, 17)
echo "[5/10] Verifying / Generating Production Environment (${ENV_FILE})..."
if [ ! -f "${ENV_FILE}" ]; then
    echo "  Generating new production secrets..."
    GEN_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    echo "--------------------------------------------------"
    echo "Please configure the production credentials:"
    read -rp "Enter GROQ_API_KEY: " INPUT_GROQ_API_KEY
    read -rp "Enter strong ADMIN_PASSWORD: " INPUT_ADMIN_PASSWORD
    read -rp "Enter Public Domain (e.g. ava.yourdomain.com or <ip>.sslip.io): " INPUT_DOMAIN
    echo "--------------------------------------------------"

    cat << EOF > "${ENV_FILE}"
# Ava AI Production Environment Configuration
ENVIRONMENT=production
SESSION_HTTPS_ONLY=true
ENABLE_CODE_EXECUTION=false
GROQ_MODEL=openai/gpt-oss-120b
PRODUCT_EVENT_RETENTION_DAYS=60
DB_PATH=/app/data/neurosupport.db
UPLOAD_DIR=/app/data/uploads
REVIEW_IMAGE_DIR=/app/data/review_images
SECRET_KEY=${GEN_SECRET_KEY}
GROQ_API_KEY=${INPUT_GROQ_API_KEY}
ADMIN_PASSWORD=${INPUT_ADMIN_PASSWORD}
ALLOWED_ORIGINS=https://${INPUT_DOMAIN}
EOF
    chmod 600 "${ENV_FILE}"
    echo "  [PASS] ${ENV_FILE} created with mode 600."
else
    echo "  [INFO] Existing ${ENV_FILE} found. Preserving current secrets."
fi

# Step 6: Build Docker Container on ARM64 (Step 18)
echo "[6/10] Building Ava AI Docker Image (ARM64)..."
docker build -t ava-ai:beta .

# Step 7: Run Ava Container (Step 19)
echo "[7/10] Starting Ava AI container bound to 127.0.0.1:8000..."
docker stop ava-beta 2>/dev/null || true
docker rm ava-beta 2>/dev/null || true

docker run -d \
  --name ava-beta \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -v "${DATA_DIR}:/app/data" \
  -p 127.0.0.1:8000:8000 \
  ava-ai:beta

# Step 8: Verify Readiness & Local Health (Steps 20 & 21)
echo "[8/10] Testing local health and readiness endpoints..."
READY=false
for i in {1..30}; do
    if curl -fs "http://127.0.0.1:8000/ready" >/dev/null 2>&1; then
        READY=true
        echo "  [PASS] Ava container is healthy and ready after ${i}s."
        break
    fi
    sleep 1
done

if [ "$READY" = false ]; then
    echo "[-] ERROR: Container failed readiness check."
    docker logs --tail 50 ava-beta
    exit 1
fi

# Verify persistent mounts inside container
echo "  Verifying container volume mapping..."
docker exec ava-beta test -f /app/data/neurosupport.db || echo "  [INFO] DB initializing at /app/data/neurosupport.db"
docker exec ava-beta test -d /app/data/uploads
docker exec ava-beta test -d /app/data/review_images
echo "  [PASS] Persistent directories verified inside container."

# Step 9: Configure Caddy Reverse Proxy & TLS (Steps 22, 24, 25)
echo "[9/10] Configuring Caddy Reverse Proxy..."
DOMAIN=$(grep -E '^ALLOWED_ORIGINS=' "${ENV_FILE}" | cut -d '=' -f2 | sed 's|https://||' | cut -d ',' -f1 | tr -d ' ')

if [ -n "$DOMAIN" ] && [ "$DOMAIN" != "yourdomain.example" ]; then
    cat << EOF > /etc/caddy/Caddyfile
${DOMAIN} {
    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto https
    }
}
EOF
    systemctl restart caddy
    echo "  [PASS] Caddy configured for domain: ${DOMAIN}"
    echo "  Caddy will automatically provision Let's Encrypt TLS certificate."
else
    echo "  [!] Warning: No domain found in ${ENV_FILE}. Update /etc/caddy/Caddyfile manually."
fi

# Step 10: Setup Automated Daily Backup Cron Job (Step 28)
echo "[10/10] Installing daily SQLite backup cron job..."
cat << 'EOF' > /etc/cron.daily/ava-backup
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/opt/ava/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/neurosupport_backup_${TIMESTAMP}.db"

mkdir -p "${BACKUP_DIR}"
# Run backup inside container using online backup utility
docker exec ava-beta python3 scripts/backup_db.py --dest "/app/data/neurosupport_hot_backup.db" >/dev/null 2>&1
# Move hot backup to host backup directory
mv /opt/ava/data/neurosupport_hot_backup.db "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}"

# Keep latest 7 backups, purge older (to stay within free disk limits)
find "${BACKUP_DIR}" -name "neurosupport_backup_*.db" -type f -mtime +7 -delete
EOF
chmod +x /etc/cron.daily/ava-backup
echo "  [PASS] Daily backup cron installed (/etc/cron.daily/ava-backup)."

echo ""
echo "======================================================================"
echo "  Ava AI Deployment Completed Successfully!"
echo "  Public URL: https://${DOMAIN}"
echo "  Local Health: curl http://127.0.0.1:8000/health -> 200"
echo "  Local Readiness: curl http://127.0.0.1:8000/ready -> 200"
echo "======================================================================"
