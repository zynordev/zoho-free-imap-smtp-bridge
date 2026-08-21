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
- Full folder sync: every Zoho folder (Inbox, Sent, Drafts, Trash, Spam, custom folders, ...) is discovered automatically and mirrored into a matching Maildir++ subfolder
- Inbound polling with SQLite duplicate protection
- Outbound delivery through Zoho Mail API
- Local Maildir delivery for Dovecot
- No credentials in the repository

The current release preserves normal text/plain and text/html content and common reply headers. Sync is one-way and additive only (Zoho -> local): the bridge never deletes or moves mail that already landed in Dovecot, even if it's deleted or moved on the Zoho side. Outbound MIME attachment upload is planned for a later release; Zoho remains the source of truth.

## Requirements

- Debian 12/13 or Ubuntu 24.04
- Root access to a VPS
- A DNS-only A record such as `mail.example.com` pointing to the VPS
- Zoho Mail API access and one OAuth refresh token per account
- Postfix, Dovecot, Python 3.11+ and a trusted TLS certificate

Do not proxy the mail hostname through Cloudflare. IMAP and SMTP need a direct DNS record.

## DNS and Zoho verification

Before starting the bridge:

1. Add an **A** record for `mail.example.com` pointing to the server IP. Keep it **DNS only**; do not proxy IMAP or SMTP through Cloudflare.
2. Keep Zoho's MX records unchanged.
3. Add the TXT record Zoho displays for domain verification. The name is usually `@` and the content is unique to your Zoho organization.
4. Wait for DNS propagation and click **Verify** in Zoho.

The bridge does not create DNS records automatically. The Zoho TXT value is account-specific and DNS providers have different APIs. The guided setup prints this checklist and asks the user to confirm that TXT verification is complete.

## Create Zoho OAuth values

For each mailbox, open the Zoho API Console for the same Zoho organization and create a **Self Client**. Generate a one-time code with these scopes:

```text
ZohoMail.accounts.READ,ZohoMail.folders.READ,ZohoMail.messages.READ,ZohoMail.messages.CREATE
```

Exchange the code immediately; it expires quickly:

```bash
curl -X POST 'https://accounts.zoho.eu/oauth/v2/token' \
  --data-urlencode 'code=ONE_TIME_CODE' \
  --data-urlencode 'client_id=CLIENT_ID' \
  --data-urlencode 'client_secret=CLIENT_SECRET' \
  --data-urlencode 'grant_type=authorization_code'
```

Store the returned `refresh_token` in the wizard. Use the Zoho Mail API `/api/accounts` endpoint with the temporary access token to obtain the mailbox `ACCOUNT_ID` (folders are discovered automatically at runtime — no per-folder ID needed). Never put these values in GitHub or a chat message.

## Quick start

```bash
sudo deploy/install.sh

# Optional guided setup; it fills /etc/mailbridge/mailbridge.env for you
# and does not change DNS automatically.
sudo bash deploy/setup-wizard.sh

# If you skipped the wizard, edit the secrets by hand instead:
$EDITOR /etc/mailbridge/mailbridge.env
```

`install.sh` already creates `/etc/mailbridge/mailbridge.env` from `.env.example` if it does not exist yet. Do not re-run `cp .env.example /etc/mailbridge/mailbridge.env` after the wizard — it has no existence check and will silently overwrite your configured secrets with the blank template.

The installer copies the bridge and helper. Edit `/etc/systemd/system/mailbridge.service` and add every configured account's **home** directory — `/vmail/<domain>/<user>`, not the `Maildir` inside it — to `ReadWritePaths` (space-separated; the shipped line covers only one example account). Naming the `Maildir` instead deadlocks the service: `ProtectSystem=strict` requires every listed path to exist at start, but the bridge is what creates the Maildir, so it can never start to create it (`status=226/NAMESPACE`). Then configure Postfix/Dovecot and OAuth, and run:

```bash
systemctl daemon-reload
systemctl enable --now mailbridge
```

Postfix must authenticate Thunderbird users on port 587 and route authenticated bridge mail to the `mailbridge` transport. Dovecot must expose virtual Maildir users on IMAPS 993. Configuration notes are in `deploy/postfix/README.md` and `deploy/dovecot/README.md`.

The wizard asks for local mailbox settings and per-account OAuth values, writes them to `/etc/mailbridge/mailbridge.env` with mode `0600`, and does not print secrets back to the terminal. It does not replace the Postfix/Dovecot configuration steps.

## Environment

Account variables are normalized. For `person@example.com` use:

```text
ZOHO_PERSON_AT_EXAMPLE_COM_ACCOUNT_ID=...
ZOHO_PERSON_AT_EXAMPLE_COM_CLIENT_ID=...
ZOHO_PERSON_AT_EXAMPLE_COM_CLIENT_SECRET=...
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

Because the bridge now syncs the real Zoho Sent folder back down, **turn off Thunderbird's own copy-to-Sent behavior for this account**: Account Settings -> Copies & Folders -> uncheck "Place a copy in". Zoho's Send API already files a Sent copy on its side, and the bridge mirrors that copy into the account's IMAP Sent folder within one poll interval. If Thunderbird's own setting stays on too, every message you send gets filed twice (Thunderbird's immediate local copy, plus the bridge's copy pulled back from Zoho a few seconds later) as two separate, unmerged entries.

## Security checklist

- Keep the mail A record DNS-only.
- Open only SSH, 993 and 587; port 25 is not required for this architecture.
- Enforce TLS and SMTP AUTH on submission.
- Restrict `From` addresses to authenticated accounts.
- Keep `.env` and OAuth refresh tokens out of Git.
- Do not log message bodies or credentials.
- Never commit `.env`, OAuth secrets, refresh tokens, mailbox passwords, or TLS private keys.

## License

MIT. See [LICENSE](LICENSE).

