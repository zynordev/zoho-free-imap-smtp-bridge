#!/usr/bin/env python3
import logging
import os
import re
import sqlite3
import time
import uuid
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlencode

import requests

LOG = logging.getLogger("mailbridge")
DB_PATH = os.getenv("MAILBRIDGE_DB", "/var/lib/mailbridge/state.sqlite3")
QUEUE = Path(os.getenv("MAILBRIDGE_QUEUE", "/var/spool/mailbridge/outbound"))
MAILDIR_ROOT = Path(os.getenv("MAILDIR_ROOT", "/vmail"))
API_BASE = os.getenv("ZOHO_API_BASE", "https://mail.zoho.eu").rstrip("/")
TOKEN_URL = os.getenv("ZOHO_TOKEN_URL", "https://accounts.zoho.eu/oauth/v2/token")
CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ACCOUNTS = [x.strip().lower() for x in os.getenv("ZOHO_ACCOUNTS", "").split(",") if x.strip()]
TOKENS = {}
FOLDER_CACHE = {}
FOLDER_CACHE_TTL = 600


def key(account, suffix):
    return "ZOHO_" + account.replace("@", "_AT_").replace(".", "_").upper() + "_" + suffix


def account_value(account, suffix):
    return os.getenv(key(account, suffix), "")


def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS processed_messages (account TEXT NOT NULL, message_id TEXT NOT NULL, processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(account, message_id))")
    conn.commit()
    return conn


RETRYABLE_STATUS = (429, 500, 502, 503, 504)


def _send(method, url, timeout, attempts=3, **kwargs):
    for attempt in range(1, attempts + 1):
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts:
                raise
            time.sleep(2 ** (attempt - 1))
            continue
        if response.status_code in RETRYABLE_STATUS and attempt < attempts:
            time.sleep(2 ** (attempt - 1))
            continue
        return response


def token(account):
    cached = TOKENS.get(account)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    refresh = account_value(account, "REFRESH_TOKEN")
    client_id = account_value(account, "CLIENT_ID") or CLIENT_ID
    client_secret = account_value(account, "CLIENT_SECRET") or CLIENT_SECRET
    if not client_id or not client_secret or not refresh:
        raise RuntimeError(f"OAuth configuration missing for {account}")
    response = _send("POST", TOKEN_URL, 30, data={"refresh_token": refresh, "client_id": client_id, "client_secret": client_secret, "grant_type": "refresh_token"})
    response.raise_for_status()
    data = response.json()
    access = data["access_token"]
    TOKENS[account] = (access, time.time() + int(data.get("expires_in", 3600)))
    return access


def api(account, method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = "Zoho-oauthtoken " + token(account)
    headers["Accept"] = "application/json"
    response = _send(method, API_BASE + path, 45, headers=headers, **kwargs)
    response.raise_for_status()
    return response


def message_rows(data):
    payload = data.get("data", data)
    if isinstance(payload, dict):
        for field in ("messages", "message", "data"):
            if isinstance(payload.get(field), list):
                return payload[field]
    return payload if isinstance(payload, list) else []


def safe_mailbox_name(name):
    # Maildir++ subfolder naming: "." separates hierarchy levels, so collapse
    # any path separators from Zoho's folder path into dots too. Keep
    # non-ASCII letters (e.g. Turkish folder names) intact; only strip
    # control characters, which are the only genuinely unsafe bytes here.
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "_", name.strip("/").replace("/", "."))
    return cleaned or "folder"


def account_folders(account):
    """Discover every Zoho folder for the account and where it lands locally.
    Returns a list of (mailbox, folder_id) where mailbox is "" for the
    account's Inbox (delivered straight into Maildir/new) or ".Name" for
    every other folder (delivered into a Maildir++ subfolder). Cached for
    FOLDER_CACHE_TTL seconds since the folder list rarely changes and this
    would otherwise cost one extra Zoho API call every poll cycle."""
    cached = FOLDER_CACHE.get(account)
    if cached and cached[1] > time.time():
        return cached[0]
    account_id = account_value(account, "ACCOUNT_ID")
    data = api(account, "GET", f"/api/accounts/{account_id}/folders").json()
    payload = data.get("data", data)
    rows = payload if isinstance(payload, list) else []
    folders = []
    for row in rows:
        folder_id = str(row.get("folderId") or "")
        if not folder_id:
            continue
        path = str(row.get("path") or "").strip()
        name = str(row.get("folderName") or "").strip()
        # Zoho reports folderType=Inbox for user-created top-level folders
        # too (a "Newsletter" folder comes back as type Inbox), so the type
        # alone cannot identify the real INBOX — match the path instead.
        # Prefer the path for naming as well, so nested folders keep their
        # hierarchy: "/Work/Invoices" -> ".Work.Invoices".
        if path == "/Inbox" or (not path and name.lower() == "inbox"):
            folders.append(("", folder_id))
        else:
            folders.append(("." + safe_mailbox_name(path or name or folder_id), folder_id))
    FOLDER_CACHE[account] = (folders, time.time() + FOLDER_CACHE_TTL)
    return folders


def deliver_maildir(account, mailbox, raw):
    local, domain = account.split("@", 1)
    base = MAILDIR_ROOT / domain / local / "Maildir"
    new_dir = (base / mailbox / "new") if mailbox else (base / "new")
    new_dir.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time())}.{os.getpid()}.{uuid.uuid4().hex}.mailbridge"
    # Keep temp and final files on the same filesystem for hardened systemd units.
    tmp_path = new_dir / ("." + name + ".tmp")
    tmp_path.write_bytes(raw.encode("utf-8", errors="replace"))
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, new_dir / name)


def inbound(account):
    account_id = account_value(account, "ACCOUNT_ID")
    if not account_id:
        LOG.error("account ID missing account=%s", account)
        return
    try:
        folders = account_folders(account)
    except Exception:
        LOG.exception("folder discovery failed account=%s", account)
        return
    conn = db()
    try:
        for mailbox, folder_id in folders:
            query = urlencode({"folderId": folder_id, "limit": 50})
            try:
                rows = message_rows(api(account, "GET", f"/api/accounts/{account_id}/messages/view?{query}").json())
            except Exception:
                LOG.exception("folder listing failed account=%s folder_id=%s", account, folder_id)
                continue
            for row in rows:
                message_id = str(row.get("messageId") or row.get("message_id") or "")
                if not message_id or conn.execute("SELECT 1 FROM processed_messages WHERE account=? AND message_id=?", (account, message_id)).fetchone():
                    continue
                try:
                    raw_data = api(account, "GET", f"/api/accounts/{account_id}/messages/{message_id}/originalmessage").json()
                    payload = raw_data.get("data", raw_data)
                    raw = payload.get("content", "") if isinstance(payload, dict) else ""
                    if not raw:
                        LOG.warning("inbound message has no MIME content account=%s message_id=%s", account, message_id)
                        continue
                    deliver_maildir(account, mailbox, raw)
                except Exception:
                    # Isolate one bad message so it cannot block the rest of the batch;
                    # it stays unprocessed and is retried next cycle.
                    LOG.exception("inbound message failed account=%s mailbox=%s message_id=%s", account, mailbox or "INBOX", message_id)
                    continue
                conn.execute("INSERT INTO processed_messages(account,message_id) VALUES(?,?)", (account, message_id))
                conn.commit()
                LOG.info("inbound delivered account=%s mailbox=%s message_id=%s", account, mailbox or "INBOX", message_id)
    finally:
        conn.close()


def addresses(value):
    return ", ".join(x.strip() for x in value.split(",") if x.strip())


def quarantine(path, meta, reason):
    """Move a permanently undeliverable message out of the queue.

    Without this the message stays in the queue and is retried every poll
    cycle forever (a few times a minute), filling the log and never
    succeeding, because nothing about it can change on its own. Keep the
    file rather than deleting it so the mail is not silently lost.
    """
    failed = QUEUE / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    path.replace(failed / path.name)
    if meta.exists():
        meta.replace(failed / meta.name)
    LOG.error("outbound quarantined file=%s reason=%s", path.name, reason)


def outbound_file(path):
    meta = Path(str(path) + ".meta")
    if not meta.exists():
        return
    values = {}
    for line in meta.read_text(errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            values[k] = v
    sender = values.get("sender", "").lower()
    if sender not in ACCOUNTS:
        # Permanent: this sender will never become configured by itself.
        # Typically local system mail (cron, sudo, logwatch) that reached
        # the transport; route those to discard: in Postfix instead.
        quarantine(path, meta, f"sender not configured: {sender}")
        return
    account_id = account_value(sender, "ACCOUNT_ID")
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body = msg.get_body(preferencelist=("html", "plain")) if msg.is_multipart() else msg
    content = body.get_content() if body else ""
    payload = {"fromAddress": sender, "toAddress": addresses(msg.get("To", "")), "subject": str(msg.get("Subject", "")), "content": content, "mailFormat": "html" if body and body.get_content_type() == "text/html" else "plaintext", "encoding": "UTF-8"}
    if msg.get("Cc"):
        payload["ccAddress"] = addresses(msg.get("Cc", ""))
    if values.get("recipients"):
        payload["bccAddress"] = addresses(values["recipients"])
    api(sender, "POST", f"/api/accounts/{account_id}/messages", json=payload)
    path.unlink()
    meta.unlink(missing_ok=True)
    LOG.info("outbound sent account=%s file=%s", sender, path.name)


def outbound():
    QUEUE.mkdir(parents=True, exist_ok=True)
    for path in sorted(QUEUE.glob("message.*.eml")):
        try:
            outbound_file(path)
        except Exception:
            LOG.exception("outbound failed file=%s", path.name)


def main():
    logging.basicConfig(level=os.getenv("MAILBRIDGE_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    interval = int(os.getenv("MAILBRIDGE_INTERVAL", "10"))
    while True:
        outbound()
        for account in ACCOUNTS:
            try:
                inbound(account)
            except Exception:
                LOG.exception("inbound failed account=%s", account)
        time.sleep(interval)


if __name__ == "__main__":
    main()

