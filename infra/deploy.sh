#!/bin/bash
# SwarmChain Production Deployment
# Run on a fresh Ubuntu 24.04 DigitalOcean droplet.
#
# Usage:
#   bash deploy.sh <domain>
#   bash deploy.sh swarmchain.example.com
#
# Idempotent — safe to re-run.

set -euo pipefail

# ── Arguments ─────────────────────────────────────────────
DOMAIN="${1:?Usage: deploy.sh <domain>}"
REPO="https://github.com/SudoSuOps/Swarn-chain.git"
APP_DIR="/opt/swarmchain"
COMPOSE_FILE="infra/docker-compose.prod.yml"
SWARMCHAIN_USER="swarmchain"

echo "============================================"
echo " SwarmChain Production Deploy"
echo " Domain : ${DOMAIN}"
echo " Target : ${APP_DIR}"
echo "============================================"

# ── 1. System packages ───────────────────────────────────
echo "[1/12] Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

echo "[1/12] Installing prerequisites..."
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release \
    git ufw jq

# ── 2. Install Docker (if not present) ───────────────────
if ! command -v docker &>/dev/null; then
    echo "[2/12] Installing Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "[2/12] Docker already installed, skipping."
fi

systemctl enable --now docker

# ── 3. Create system user ────────────────────────────────
if ! id "${SWARMCHAIN_USER}" &>/dev/null; then
    echo "[3/12] Creating ${SWARMCHAIN_USER} user..."
    useradd --system --create-home --shell /usr/sbin/nologin "${SWARMCHAIN_USER}"
    usermod -aG docker "${SWARMCHAIN_USER}"
else
    echo "[3/12] User ${SWARMCHAIN_USER} already exists, skipping."
fi

# ── 4. Clone or update repository ────────────────────────
if [ -d "${APP_DIR}/.git" ]; then
    echo "[4/12] Repository exists, pulling latest..."
    git -C "${APP_DIR}" pull --ff-only || true
else
    echo "[4/12] Cloning repository..."
    rm -rf "${APP_DIR}"
    git clone "${REPO}" "${APP_DIR}"
fi

chown -R "${SWARMCHAIN_USER}:${SWARMCHAIN_USER}" "${APP_DIR}"

# ── 5. Generate .env.prod (only if missing) ──────────────
ENV_FILE="${APP_DIR}/infra/.env.prod"
if [ ! -f "${ENV_FILE}" ]; then
    echo "[5/12] Generating .env.prod with random secrets..."
    PG_PASSWORD=$(openssl rand -hex 32)
    API_KEY=$(openssl rand -hex 32)

    sed \
        -e "s|\${PG_PASSWORD}|${PG_PASSWORD}|g" \
        -e "s|\${API_KEY}|${API_KEY}|g" \
        -e "s|\${DOMAIN}|${DOMAIN}|g" \
        "${APP_DIR}/infra/.env.prod.template" > "${ENV_FILE}"

    chmod 600 "${ENV_FILE}"
    chown "${SWARMCHAIN_USER}:${SWARMCHAIN_USER}" "${ENV_FILE}"

    echo ""
    echo "  !! SAVE THESE CREDENTIALS !!"
    echo "  Postgres password : ${PG_PASSWORD}"
    echo "  API key           : ${API_KEY}"
    echo ""
else
    echo "[5/12] .env.prod already exists, preserving secrets."
    # Extract existing values for display
    API_KEY=$(grep '^SWARMCHAIN_API_KEY=' "${ENV_FILE}" | cut -d= -f2)
fi

# ── 6. Patch nginx configs with actual domain ────────────
echo "[6/12] Patching nginx configs with domain ${DOMAIN}..."
sed -i "s/swarmchain\.example\.com/${DOMAIN}/g" \
    "${APP_DIR}/infra/nginx/nginx.initial.conf" \
    "${APP_DIR}/infra/nginx/nginx.prod.conf"

# ── 7. Start with HTTP-only nginx (for certbot) ──────────
echo "[7/12] Deploying with HTTP-only nginx config..."
cp "${APP_DIR}/infra/nginx/nginx.initial.conf" \
   "${APP_DIR}/infra/nginx/nginx.active.conf"

cd "${APP_DIR}"
docker compose -f "${COMPOSE_FILE}" up -d --build

# ── 8. Wait for backend health ───────────────────────────
echo "[8/12] Waiting for backend health check..."
RETRIES=30
until curl -sf http://localhost/health > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "${RETRIES}" -le 0 ]; then
        echo "ERROR: Backend failed to become healthy after 60 seconds."
        echo "Check logs: docker compose -f ${COMPOSE_FILE} logs backend"
        exit 1
    fi
    sleep 2
done
echo "  Backend is healthy."

# ── 9. Obtain SSL certificate ────────────────────────────
echo "[9/12] Obtaining SSL certificate via certbot..."
apt-get install -y -qq certbot

# Create webroot directory inside the certbot_www volume
CERTBOT_WEBROOT=$(docker volume inspect "${APP_DIR##*/}_certbot_www" --format '{{.Mountpoint}}' 2>/dev/null || true)
if [ -z "${CERTBOT_WEBROOT}" ]; then
    # Compose project name is the directory basename
    PROJECT_NAME=$(basename "${APP_DIR}")
    CERTBOT_WEBROOT=$(docker volume inspect "${PROJECT_NAME}_certbot_www" --format '{{.Mountpoint}}' 2>/dev/null || true)
fi

# Fall back to using the Docker volume mount path
if [ -z "${CERTBOT_WEBROOT}" ]; then
    CERTBOT_WEBROOT="/var/www/certbot"
    mkdir -p "${CERTBOT_WEBROOT}"
fi

# Run certbot (skip if cert already exists)
if [ ! -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
    certbot certonly \
        --webroot \
        --webroot-path "${CERTBOT_WEBROOT}" \
        --domain "${DOMAIN}" \
        --non-interactive \
        --agree-tos \
        --email "admin@${DOMAIN}" \
        --no-eff-email
else
    echo "  SSL cert for ${DOMAIN} already exists, skipping."
fi

# Copy certs into the Docker volume so nginx can read them
CERT_VOL=$(docker volume inspect "${PROJECT_NAME:-swarmchain}_certbot_etc" --format '{{.Mountpoint}}' 2>/dev/null || true)
if [ -n "${CERT_VOL}" ] && [ -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
    cp -rL /etc/letsencrypt/* "${CERT_VOL}/" 2>/dev/null || true
fi

# ── 10. Switch to SSL nginx config ──────────────────────
echo "[10/12] Switching to SSL nginx config..."
cp "${APP_DIR}/infra/nginx/nginx.prod.conf" \
   "${APP_DIR}/infra/nginx/nginx.active.conf"

# ── 11. Restart nginx with SSL ──────────────────────────
echo "[11/12] Restarting nginx..."
docker compose -f "${COMPOSE_FILE}" restart nginx

# Verify HTTPS is working
sleep 3
if curl -sf "https://${DOMAIN}/health" > /dev/null 2>&1; then
    echo "  HTTPS is working."
else
    echo "  WARNING: HTTPS check failed. Check cert paths and nginx logs."
    echo "  Falling back — HTTP is still working."
fi

# ── 12. Certbot auto-renewal + UFW ──────────────────────
echo "[12/12] Configuring firewall and cert auto-renewal..."

# Certbot renewal cron (idempotent — checks before adding)
CRON_CMD="0 3 * * * certbot renew --quiet --deploy-hook 'docker compose -f ${APP_DIR}/${COMPOSE_FILE} restart nginx'"
( crontab -l 2>/dev/null | grep -qF "certbot renew" ) || \
    ( crontab -l 2>/dev/null; echo "${CRON_CMD}" ) | crontab -

# UFW firewall
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP"
ufw allow 443/tcp  comment "HTTPS"
ufw --force enable

echo ""
echo "============================================"
echo " SwarmChain deployed successfully!"
echo "============================================"
echo ""
echo " Dashboard : https://${DOMAIN}/"
echo " Health    : https://${DOMAIN}/health"
echo " Metrics   : https://${DOMAIN}/metrics"
echo " API base  : https://${DOMAIN}/api/"
echo ""
echo " API key   : ${API_KEY}"
echo ""
echo " Start mining from your local machine:"
echo "   python mine_1000.py \\"
echo "     --api-url https://${DOMAIN} \\"
echo "     --api-key ${API_KEY}"
echo ""
echo " Logs:"
echo "   cd ${APP_DIR}"
echo "   docker compose -f ${COMPOSE_FILE} logs -f"
echo ""
echo " Postgres backup:"
echo "   docker compose -f ${COMPOSE_FILE} exec postgres \\"
echo "     pg_dump -U swarmchain swarmchain > backup_\$(date +%Y%m%d).sql"
echo ""
