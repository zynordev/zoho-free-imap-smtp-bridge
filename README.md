# Zoho Free IMAP/SMTP Bridge

Use Zoho Mail as the real mail provider while exposing a normal IMAP/SMTP endpoint for Thunderbird and other mail clients.

```text
Internet -> Zoho MX -> Zoho API -> Mail Bridge -> Dovecot -> IMAP client
IMAP/SMTP client -> Postfix -> Mail Bridge -> Zoho API -> recipient
```

Zoho remains responsible for Internet delivery. The VPS is only a local IMAP/SMTP front end, which is useful when direct Zoho IMAP/POP access is unavailable or undesirable.

## Features

- OAuth 2.0 refresh-token authentication
- Multiple Zoho accounts on one bridge
- Inbound polling with SQLite duplicate protection
- Outbound delivery through Zoho Mail API
- Local Maildir delivery for Dovecot
- No credentials in the repository

The current release preserves normal text/plain and text/html content and common reply headers. Full folder synchronization and outbound MIME attachment upload are planned for a later release; Zoho remains the source of truth.

## Requirements

- Debian 12/13 or Ubuntu 24.04
- Root access to a VPS
- A DNS-only A record such as `mail.example.com` pointing to the VPS
- Zoho Mail API access and one OAuth refresh token per account
- Postfix, Dovecot, Python 3.11+ and a trusted TLS certificate

Do not proxy the mail hostname through Cloudflare. IMAP and SMTP need a direct DNS record.

## Quick start

```bash
sudo deploy/install.sh

# Then edit the generated secret file.
/opt/mailbridge/venv/bin/pip install -r requirements.txt
install -d -m 0750 /etc/mailbridge
cp .env.example /etc/mailbridge/mailbridge.env
chmod 0640 /etc/mailbridge/mailbridge.env
$EDITOR /etc/mailbridge/mailbridge.env
```

The installer copies the bridge and helper. Replace the example Maildir path in `ReadWritePaths` for every account, configure Postfix/Dovecot and OAuth, then run:

```bash
systemctl daemon-reload
systemctl enable --now mailbridge
```

Postfix must authenticate Thunderbird users on port 587 and route authenticated bridge mail to the `mailbridge` transport. Dovecot must expose virtual Maildir users on IMAPS 993. Configuration notes are in `deploy/postfix/README.md` and `deploy/dovecot/README.md`.

## Environment

Account variables are normalized. For `person@example.com` use:

```text
ZOHO_PERSON_AT_EXAMPLE_COM_ACCOUNT_ID=...
ZOHO_PERSON_AT_EXAMPLE_COM_FOLDER_ID=...
ZOHO_PERSON_AT_EXAMPLE_COM_REFRESH_TOKEN=...
```

Keep the refresh token, client secret, mailbox passwords and TLS private keys outside Git. Rotate any credential that is exposed.

## Thunderbird

| Setting | Value |
|---|---|
| IMAP host | `mail.example.com` |
| IMAP port | `993` |
| IMAP security | SSL/TLS |
| SMTP host | `mail.example.com` |
| SMTP port | `587` |
| SMTP security | STARTTLS |
| Authentication | Normal password |
| Username | Full email address |

The Thunderbird password is the local Dovecot/Postfix password, not the Zoho password.

## Security checklist

- Keep the mail A record DNS-only.
- Open only SSH, 993 and 587; port 25 is not required for this architecture.
- Enforce TLS and SMTP AUTH on submission.
- Restrict `From` addresses to authenticated accounts.
- Keep `.env` and OAuth refresh tokens out of Git.
- Do not log message bodies or credentials.

## License

MIT. See [LICENSE](LICENSE).

