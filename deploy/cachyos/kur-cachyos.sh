#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bu script root yetkisiyle calistirilmalidir: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

echo "=== 1. CachyOS / Arch Paketleri Kuruluyor ==="
pacman -S --needed --noconfirm dovecot postfix python python-requests openssl

echo "=== 2. Kullanici ve Gruplar Olusturuluyor ==="
getent group vmail >/dev/null 2>&1 || groupadd -g 5000 vmail
id vmail >/dev/null 2>&1 || useradd -u 5000 -g vmail -s /usr/bin/nologin -d /vmail -M vmail

getent group mailbridge >/dev/null 2>&1 || groupadd --system mailbridge
id mailbridge >/dev/null 2>&1 || useradd --system -g mailbridge -s /usr/bin/nologin -d /var/lib/mailbridge -M mailbridge
usermod -aG vmail mailbridge

echo "=== 3. Dizin Yapisi ve Izinler Hazirlaniyor ==="
mkdir -p /opt/mailbridge
mkdir -p /var/lib/mailbridge
mkdir -p /var/spool/mailbridge/outbound/failed
mkdir -p /etc/mailbridge
mkdir -p /vmail
mkdir -p /etc/dovecot
mkdir -p /etc/ssl/certs
mkdir -p /etc/ssl/private

chown -R root:mailbridge /opt/mailbridge
chmod 750 /opt/mailbridge

chown -R mailbridge:mailbridge /var/lib/mailbridge
chmod 750 /var/lib/mailbridge

chown -R mailbridge:mailbridge /var/spool/mailbridge
chmod 770 /var/spool/mailbridge
chmod 770 /var/spool/mailbridge/outbound

chown -R vmail:vmail /vmail
chmod 2770 /vmail

echo "=== 4. Yerel SSL Sertifikasi Uretiliyor (localhost / 127.0.0.1) ==="
if [ ! -f /etc/ssl/private/mailbridge-key.pem ] || [ ! -f /etc/ssl/certs/mailbridge-cert.pem ]; then
  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -subj "/C=TR/ST=Samsun/L=Atakum/O=HKYazilim/CN=localhost" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    -keyout /etc/ssl/private/mailbridge-key.pem \
    -out /etc/ssl/certs/mailbridge-cert.pem
  chmod 600 /etc/ssl/private/mailbridge-key.pem
  chmod 644 /etc/ssl/certs/mailbridge-cert.pem
  echo "Yerel SSL sertifikasi olusturuldu."
fi

echo "=== 5. Mailbridge Servisi Kuruluyor ==="
cp "$REPO_ROOT/mailbridge.py" /opt/mailbridge/mailbridge.py
chown root:mailbridge /opt/mailbridge/mailbridge.py
chmod 750 /opt/mailbridge/mailbridge.py

python3 -m venv --system-site-packages /opt/mailbridge/venv
/opt/mailbridge/venv/bin/pip install --upgrade pip requests >/dev/null 2>&1 || true

ENV_SRC="$SCRIPT_DIR/conf/mailbridge.env"
[ -f "$ENV_SRC" ] || ENV_SRC="$SCRIPT_DIR/conf/mailbridge.env.example"
cp "$ENV_SRC" /etc/mailbridge/mailbridge.env
chown root:mailbridge /etc/mailbridge/mailbridge.env
chmod 640 /etc/mailbridge/mailbridge.env

cp "$SCRIPT_DIR/conf/mailbridge-submit" /usr/local/sbin/mailbridge-submit
chmod 755 /usr/local/sbin/mailbridge-submit

cp "$SCRIPT_DIR/conf/mailbridge.service" /etc/systemd/system/mailbridge.service

echo "=== 6. Dovecot Yapilandiriliyor ==="
rm -rf /etc/dovecot/conf.d 2>/dev/null || true
cp "$SCRIPT_DIR/conf/dovecot.conf" /etc/dovecot/dovecot.conf

USERS_SRC="$SCRIPT_DIR/conf/users"
[ -f "$USERS_SRC" ] || USERS_SRC="$SCRIPT_DIR/conf/users.example"
cp "$USERS_SRC" /etc/dovecot/users
chown root:vmail /etc/dovecot/users
chmod 640 /etc/dovecot/users

echo "=== 7. Postfix Yapilandiriliyor ==="
cp "$SCRIPT_DIR/conf/main.cf" /etc/postfix/main.cf
cp "$SCRIPT_DIR/conf/master.cf" /etc/postfix/master.cf

SLM_SRC="$SCRIPT_DIR/conf/sender_login_maps"
[ -f "$SLM_SRC" ] || SLM_SRC="$SCRIPT_DIR/conf/sender_login_maps.example"
cp "$SLM_SRC" /etc/postfix/sender_login_maps

TR_SRC="$SCRIPT_DIR/conf/transport"
[ -f "$TR_SRC" ] || TR_SRC="$SCRIPT_DIR/conf/transport.example"
cp "$TR_SRC" /etc/postfix/transport

postmap /etc/postfix/sender_login_maps
postmap /etc/postfix/transport

postfix check >/dev/null 2>&1 || true

echo "=== 8. Servisler Baslatiliyor ==="
systemctl daemon-reload
systemctl enable --now dovecot postfix mailbridge

echo ""
echo "========================================"
echo "          KURULUM TAMAMLANDI!           "
echo "========================================"
echo "Dovecot:    $(systemctl is-active dovecot)"
echo "Postfix:    $(systemctl is-active postfix)"
echo "Mailbridge: $(systemctl is-active mailbridge)"
echo ""
echo "Thunderbird Ayarlari:"
echo "----------------------------------------"
echo "Gelen Sunucu (IMAP): 127.0.0.1 - Port: 993"
echo "Guvenlik:            SSL/TLS - Normal Parola"
echo ""
echo "Giden Sunucu (SMTP): 127.0.0.1 - Port: 587"
echo "Guvenlik:            STARTTLS - Normal Parola"
echo "----------------------------------------"
