#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=${MAILBRIDGE_ENV_FILE:-/etc/mailbridge/mailbridge.env}

echo "Zoho Free IMAP/SMTP Bridge setup"
echo
echo "DNS checklist (the wizard does not change DNS):"
read -r -p "Mail hostname [mail.example.com]: " MAIL_HOST
MAIL_HOST=${MAIL_HOST:-mail.example.com}
read -r -p "Server IPv4 address: " SERVER_IP
echo "Add this DNS-only record: A ${MAIL_HOST} ${SERVER_IP}"
echo "Keep Zoho MX records unchanged and add the TXT value shown by Zoho for domain verification."
read -r -p "Have you added and verified Zoho's TXT record? [y/N]: " TXT_OK
case "${TXT_OK,,}" in
  y|yes) ;;
  *) echo "Add the Zoho TXT record and rerun this wizard after verification."; exit 1 ;;
esac

read -r -p "Zoho account email: " ACCOUNT
ACCOUNT=${ACCOUNT,,}
KEY=$(printf '%s' "$ACCOUNT" | sed -e 's/@/_AT_/' -e 's/\./_/g' | tr '[:lower:]' '[:upper:]')
KEY="ZOHO_${KEY}"
read -r -p "Zoho account ID: " ACCOUNT_ID
read -r -p "Zoho Inbox folder ID: " FOLDER_ID
read -r -p "Zoho OAuth client ID: " CLIENT_ID
read -r -s -p "Zoho OAuth client secret: " CLIENT_SECRET; echo
read -r -s -p "Zoho OAuth refresh token: " REFRESH_TOKEN; echo
read -r -p "Polling interval seconds [5]: " INTERVAL
INTERVAL=${INTERVAL:-5}

install -d -m 0750 "$(dirname "$ENV_FILE")"
umask 077
cat > "$ENV_FILE" <<EOF
ZOHO_API_BASE=https://mail.zoho.eu
ZOHO_TOKEN_URL=https://accounts.zoho.eu/oauth/v2/token
ZOHO_ACCOUNTS=$ACCOUNT
MAILBRIDGE_INTERVAL=$INTERVAL
MAILBRIDGE_DB=/var/lib/mailbridge/state.sqlite3
MAILBRIDGE_QUEUE=/var/spool/mailbridge/outbound
MAILBRIDGE_LOG_LEVEL=INFO
${KEY}_ACCOUNT_ID=$ACCOUNT_ID
${KEY}_FOLDER_ID=$FOLDER_ID
${KEY}_CLIENT_ID=$CLIENT_ID
${KEY}_CLIENT_SECRET=$CLIENT_SECRET
${KEY}_REFRESH_TOKEN=$REFRESH_TOKEN
EOF
chmod 0600 "$ENV_FILE"

echo
echo "Secret configuration written to $ENV_FILE."
echo "Next configure Dovecot/Postfix and TLS for $MAIL_HOST, then run:"
echo "  systemctl daemon-reload && systemctl enable --now mailbridge"

