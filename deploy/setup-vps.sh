#!/usr/bin/env bash
# NexCYR VPS bootstrap — Debian 12/13 or Ubuntu 22.04/24.04.
#
# Run as a sudo-capable user on the host that will be the NexCYR Cloud:
#   git clone https://github.com/Hafsa-Khan01/NexCYR.git /tmp/nexcyr-src
#   cd /tmp/nexcyr-src && sudo bash deploy/setup-vps.sh
#
# The script is idempotent and never deletes data: an existing database or
# reports directory at /var/lib/nexcyr is left exactly as found.

set -euo pipefail

APP_DIR=/opt/nexcyr
DATA_DIR=/var/lib/nexcyr
SERVICE_USER=nexcyr
PY=${PYTHON:-python3}

log()  { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$1"; }

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash deploy/setup-vps.sh" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log "Source tree: $SRC_DIR"

log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  "${PY}" "${PY}-venv" git nginx rsync sqlite3 ca-certificates >/dev/null

log "Creating service user '${SERVICE_USER}'"
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  adduser --system --group --home "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
else
  warn "User already exists, keeping it."
fi

log "Installing application to ${APP_DIR}"
mkdir -p "${APP_DIR}"
# Copy instead of symlink so the running service is not tied to the clone dir.
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '*.db' --exclude 'reports' \
  "${SRC_DIR}"/ "${APP_DIR}"/ 2>/dev/null \
  || { warn "rsync unavailable, falling back to cp"; \
       cp -r "${SRC_DIR}"/. "${APP_DIR}"/; \
       rm -rf "${APP_DIR}/.git" "${APP_DIR}/.venv"; }

log "Creating virtualenv and installing pinned dependencies"
[[ -d "${APP_DIR}/.venv" ]] || "${PY}" -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

log "Preparing state directory ${DATA_DIR}"
mkdir -p "${DATA_DIR}/reports"
# Existing database files are preserved untouched.
if [[ -f "${DATA_DIR}/nexcyr.db" ]]; then
  warn "Found existing database at ${DATA_DIR}/nexcyr.db — it will be reused, not overwritten."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" "${DATA_DIR}"
chmod 750 "${DATA_DIR}"
chmod 700 "${DATA_DIR}/reports"

log "Installing systemd unit"
install -m 0644 "${SRC_DIR}/deploy/nexcyr.service" /etc/systemd/system/nexcyr.service
systemctl daemon-reload
systemctl enable nexcyr >/dev/null 2>&1

log "Installing nginx site"
install -m 0644 "${SRC_DIR}/deploy/nginx-upgrade-map.conf" /etc/nginx/conf.d/nexcyr-upgrade-map.conf
if [[ -f /etc/nginx/sites-available/nexcyr ]]; then
  warn "/etc/nginx/sites-available/nexcyr already exists — not overwriting your TLS config."
else
  install -m 0644 "${SRC_DIR}/deploy/nginx.conf" /etc/nginx/sites-available/nexcyr
  ln -sf /etc/nginx/sites-available/nexcyr /etc/nginx/sites-enabled/nexcyr
fi
# The stock default site is left in place on purpose — it may serve other content
# on this host. Remove it yourself if this box is dedicated to NexCYR:
#   sudo rm /etc/nginx/sites-enabled/default
if [[ -e /etc/nginx/sites-enabled/default ]]; then
  warn "Leaving /etc/nginx/sites-enabled/default in place (it only answers for unmatched hostnames)."
fi

if nginx -t >/dev/null 2>&1; then
  systemctl reload nginx
  log "nginx reloaded."
else
  warn "nginx config test failed. This is expected until the certificate paths in"
  warn "deploy/nginx.conf point at a real hostname. Fix it, then: sudo nginx -t && sudo systemctl reload nginx"
fi

log "Starting NexCYR"
systemctl restart nexcyr
sleep 3
systemctl --no-pager --lines=5 status nexcyr || true

cat <<'EOF'

--------------------------------------------------------------------------
NexCYR is installed.

Next steps:
  1. Edit /etc/nginx/sites-available/nexcyr and replace nexcyr.example.com
     with your real hostname, then:
         sudo nginx -t && sudo systemctl reload nginx
         sudo certbot --nginx -d your.hostname
  2. Optional AI provider keys (never commit these):
         sudoedit /opt/nexcyr/.env
     using .env.example as the template. Without them NexCYR runs on its
     local Intelligence Fallback Engine.
  3. Verify:  curl -k https://your.hostname/health
  4. Logs:    sudo journalctl -u nexcyr -f

Database : /var/lib/nexcyr/nexcyr.db   (survives redeploys)
Reports  : /var/lib/nexcyr/reports/
Back up  : sudo -u nexcyr sqlite3 /var/lib/nexcyr/nexcyr.db ".backup '/root/nexcyr-$(date +%F).db'"

NOTE ON SCANNING: nmap is intentionally NOT installed here. Scanning from a
public cloud host can breach provider ToS and may touch networks you are not
authorized to test. Enroll an Agent inside each explicitly authorized target
network and route scans to it; the Cloud itself reports NMAP_UNAVAILABLE.
--------------------------------------------------------------------------
EOF
