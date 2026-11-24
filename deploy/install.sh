#!/usr/bin/env bash
# Idempotent VPS installer: creates a dedicated user, venv, systemd unit.
# Run as root on a fresh Debian/Ubuntu VPS:
#   curl -fsSL <raw install.sh> | sudo bash
set -euo pipefail

APP_USER="solanachat"
APP_DIR="/opt/solana-chat"
ENV_DIR="/etc/solana-chat"
STATE_DIR="/var/lib/solana-chat"
REPO="${REPO:-https://gitlab.com/inspectorai/inspectorai-solana-chat.git}"
REF="${REF:-main}"

if [[ $EUID -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl ca-certificates >/dev/null

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR" "$STATE_DIR"
install -d -m 0750 "$ENV_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --depth 1 --branch "$REF" "$REPO" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --depth 1 origin "$REF"
  git -C "$APP_DIR" reset --hard "origin/$REF"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet "$APP_DIR"

if [[ ! -f "$ENV_DIR/env" ]]; then
  cat >"$ENV_DIR/env" <<ENV
SOLANA_CHAT_API_KEY=$(head -c 24 /dev/urandom | base64 | tr -d '=+/')
SOLANA_CHAT_SESSION_FILE=$STATE_DIR/session.json
SOLANA_CHAT_HOST=127.0.0.1
SOLANA_CHAT_PORT=20129
ENV
  chmod 0640 "$ENV_DIR/env"
  chown root:"$APP_USER" "$ENV_DIR/env"
fi

install -m 0644 "$APP_DIR/deploy/solana-chat.service" /etc/systemd/system/solana-chat.service
systemctl daemon-reload
systemctl enable --now solana-chat.service

sleep 2
if curl -fsS http://127.0.0.1:20129/v1/health >/dev/null; then
  echo "bridge healthy on http://127.0.0.1:20129/v1"
  echo "api key: $(grep SOLANA_CHAT_API_KEY "$ENV_DIR/env" | cut -d= -f2)"
else
  echo "service started but health check failed; journalctl -u solana-chat -n 60" >&2
  exit 1
fi
