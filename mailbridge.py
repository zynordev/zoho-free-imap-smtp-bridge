#!/usr/bin/env python3
import logging
import os
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


def token(account):
    cached = TOKENS.get(account)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    refresh = account_value(account, "REFRESH_TOKEN")
    if not CLIENT_ID or not CLIENT_SECRET or not refresh:
        raise RuntimeError(f"OAuth configuration missing for {account}")
    response = requests.post(TOKEN_URL, data={"refresh_token": refresh, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "refresh_token"}, timeout=30)
    response.raise_for_status()
    data = response.json()
    access = data["access_token"]
    TOKENS[account] = (access, time.time() + int(data.get("expires_in", 3600)))
    return access


def api(account, method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = "Zoho-oauthtoken " + token(account)
    headers["Accept"] = "application/json"
    response = requests.request(method, API_BASE + path, headers=headers, timeout=45, **kwargs)
    response.raise_for_status()
    return response


def message_rows(data):
    payload = data.get("data", data)
    if isinstance(payload, dict):
        for field in ("messages", "message", "data"):
            if isinstance(payload.get(field), list):
                return payload[field]
    return payload if isinstance(payload, list) else []


def deliver_maildir(account, raw):
    local, domain = account.split("@", 1)
    new_dir = MAILDIR_ROOT / domain / local / "Maildir" / "new"
    new_dir.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time())}.{os.getpid()}.{uuid.uuid4().hex}.mailbridge"
    # Keep temp and final files on the same filesystem for hardened systemd units.
    tmp_path = new_dir / ("." + name + ".tmp")
    tmp_path.write_bytes(raw.encode())
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, new_dir / name)


def inbound(account):
    account_id = account_value(account, "ACCOUNT_ID")
    folder_id = account_value(account, "FOLDER_ID") or "INBOX"
    if not account_id:
        LOG.error("account ID missing account=%s", account)
        return
    query = urlencode({"folderId": folder_id, "limit": 50})
    rows = message_rows(api(account, "GET", f"/api/accounts/{account_id}/messages/view?{query}").json())
    conn = db()
    try:
        for row in rows:
            message_id = str(row.get("messageId") or row.get("message_id") or "")
            if not message_id or conn.execute("SELECT 1 FROM processed_messages WHERE account=? AND message_id=?", (account, message_id)).fetchone():
                continue
            raw_data = api(account, "GET", f"/api/accounts/{account_id}/messages/{message_id}/originalmessage").json()
            payload = raw_data.get("data", raw_data)
            raw = payload.get("content", "") if isinstance(payload, dict) else ""
            if not raw:
                LOG.warning("inbound message has no MIME content account=%s message_id=%s", account, message_id)
                continue
            deliver_maildir(account, raw)
            conn.execute("INSERT INTO processed_messages(account,message_id) VALUES(?,?)", (account, message_id))
            conn.commit()
            LOG.info("inbound delivered account=%s message_id=%s", account, message_id)
    finally:
        conn.close()


def addresses(value):
    return ", ".join(x.strip() for x in value.split(",") if x.strip())


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
        LOG.error("outbound sender not configured sender=%s file=%s", sender, path.name)
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

