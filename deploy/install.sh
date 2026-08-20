#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root" >&2
  exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BRIDGE_DIR=/opt/mailbridge

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip

getent group mailbridge >/dev/null || groupadd --system mailbridge
id mailbridge >/dev/null 2>&1 || useradd --system --gid mailbridge --home-dir /var/lib/mailbridge --no-create-home --shell /usr/sbin/nologin mailbridge

install -d -o root -g mailbridge -m 0750 "$BRIDGE_DIR"
install -d -o mailbridge -g mailbridge -m 0750 /var/lib/mailbridge
install -d -o root -g mailbridge -m 0750 /var/spool/mailbridge/outbound
install -m 0640 -o root -g mailbridge "$ROOT_DIR/mailbridge.py" "$BRIDGE_DIR/mailbridge.py"
install -m 0644 "$ROOT_DIR/requirements.txt" "$BRIDGE_DIR/requirements.txt"
python3 -m venv "$BRIDGE_DIR/venv"
"$BRIDGE_DIR/venv/bin/pip" install --upgrade pip
"$BRIDGE_DIR/venv/bin/pip" install -r "$BRIDGE_DIR/requirements.txt"

install -d -o root -g mailbridge -m 0750 /etc/mailbridge
if [ ! -e /etc/mailbridge/mailbridge.env ]; then
  install -m 0640 -o root -g mailbridge "$ROOT_DIR/.env.example" /etc/mailbridge/mailbridge.env
  echo "Edit /etc/mailbridge/mailbridge.env before starting the service."
fi
install -m 0755 "$ROOT_DIR/deploy/mailbridge-submit" /usr/local/sbin/mailbridge-submit
install -m 0644 "$ROOT_DIR/deploy/mailbridge.service" /etc/systemd/system/mailbridge.service
systemctl daemon-reload
echo "Bridge files installed. Configure Postfix, Dovecot, ReadWritePaths and OAuth before: systemctl enable --now mailbridge"

