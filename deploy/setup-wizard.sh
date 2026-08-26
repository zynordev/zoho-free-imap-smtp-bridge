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
# LC_ALL=C is required, not cosmetic: under a Turkish locale (tr_TR.UTF-8)
# "[:lower:]" maps i to the dotted capital I, so tr leaves every "i" alone and
# the wizard writes ZOHO_iLETiSiM_AT_... while mailbridge.py looks up
# ZOHO_ILETISIM_AT_... — the account then fails with "OAuth configuration
# missing". Replacing every non-alphanumeric character (not just ".") also
# keeps hyphenated domains from producing names systemd rejects.
KEY=$(printf '%s' "$ACCOUNT" | LC_ALL=C sed -e 's/@/_AT_/' -e 's/[^a-zA-Z0-9_]/_/g' | LC_ALL=C tr 'a-z' 'A-Z')
KEY="ZOHO_${KEY}"
read -r -p "Zoho account ID: " ACCOUNT_ID
read -r -p "Zoho OAuth client ID: " CLIENT_ID
read -r -s -p "Zoho OAuth client secret: " CLIENT_SECRET; echo
read -r -s -p "Zoho OAuth refresh token: " REFRESH_TOKEN; echo
read -r -p "Polling interval seconds [5]: " INTERVAL
INTERVAL=${INTERVAL:-5}

install -d -m 0750 "$(dirname "$ENV_FILE")"
umask 077

# Merge with any accounts already configured by a previous wizard run,
# instead of overwriting them (the bridge supports multiple accounts).
ALL_ACCOUNTS="$ACCOUNT"
if [ -f "$ENV_FILE" ]; then
  EXISTING_ACCOUNTS=$(sed -n 's/^ZOHO_ACCOUNTS=//p' "$ENV_FILE" | head -n1)
  if [ -n "$EXISTING_ACCOUNTS" ]; then
    ALL_ACCOUNTS=$(printf '%s\n%s\n' "$EXISTING_ACCOUNTS" "$ACCOUNT" | tr ',' '\n' | sed '/^$/d' | awk '!seen[$0]++' | paste -sd, -)
  fi
fi

TMP_FILE=$(mktemp)
{
  if [ -f "$ENV_FILE" ]; then
    grep -v -e '^ZOHO_ACCOUNTS=' -e "^${KEY}_" "$ENV_FILE" || true
  else
    cat <<EOF
ZOHO_API_BASE=https://mail.zoho.eu
ZOHO_TOKEN_URL=https://accounts.zoho.eu/oauth/v2/token
MAILBRIDGE_INTERVAL=$INTERVAL
MAILBRIDGE_DB=/var/lib/mailbridge/state.sqlite3
MAILBRIDGE_QUEUE=/var/spool/mailbridge/outbound
MAILBRIDGE_LOG_LEVEL=INFO
EOF
  fi
  echo "ZOHO_ACCOUNTS=$ALL_ACCOUNTS"
  echo "${KEY}_ACCOUNT_ID=$ACCOUNT_ID"
  echo "${KEY}_CLIENT_ID=$CLIENT_ID"
  echo "${KEY}_CLIENT_SECRET=$CLIENT_SECRET"
  echo "${KEY}_REFRESH_TOKEN=$REFRESH_TOKEN"
} > "$TMP_FILE"
mv "$TMP_FILE" "$ENV_FILE"
chmod 0600 "$ENV_FILE"

echo
echo "Secret configuration written to $ENV_FILE."
echo "Next configure Dovecot/Postfix and TLS for $MAIL_HOST, then run:"
echo "  systemctl daemon-reload && systemctl enable --now mailbridge"

