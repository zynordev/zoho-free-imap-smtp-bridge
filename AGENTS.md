# Zoho Free IMAP/SMTP Bridge: Ajan Rehberi (AGENTS.md)

Bu dosya Claude Code, Codex CLI ve Antigravity icin ortak calisma belgesidir.

## Genel Mimari ve CachyOS Yerel Kurulumu

[Antigravity, 2026-09-24]:
VDS (Bulutova) tasfiyesinin ardindan, servis yerel CachyOS ortamina (localhost) tasindi.
Sistem dis aglara kapali olup yalnizca 127.0.0.1 uzerinden calisir:
- Gelen Sunucu (Dovecot IMAP): 127.0.0.1:993 (SSL/TLS, yerel cert /etc/ssl/certs/mailbridge-cert.pem)
- Giden Sunucu (Postfix SMTP): 127.0.0.1:587 (STARTTLS, Dovecot SASL)
- Kopru Servisi (mailbridge.service): /opt/mailbridge/mailbridge.py (Python venv, Zoho Mail API ile senkronizasyon, 10 saniyede bir yoklar)

## Yapilandirma Dosyalari ve Konumlar

- Ortam degiskenleri ve OAuth token'lari: /etc/mailbridge/mailbridge.env (0640 root:mailbridge)
- Dovecot kullanicilari ve parolalar: /etc/dovecot/users (SHA512-CRYPT hash)
- Postfix yapilandirmasi: /etc/postfix/main.cf, /etc/postfix/master.cf (veritabani map tipi lmdb:)
- Postfix gonderici ve tasima eslesmeleri: /etc/postfix/sender_login_maps, /etc/postfix/transport
- Mail kutulari: /vmail/<domain>/<kullanici>/Maildir (sahibi vmail:vmail uid 5000, mailbridge vmail grubundadir)
- SQLite senkronizasyon durumu: /var/lib/mailbridge/state.sqlite3

## Yonetim Komutlari

- Servis durumlari: systemctl status dovecot postfix mailbridge
- Servisleri baslatma/yeniden baslatma: sudo systemctl restart dovecot postfix mailbridge
- Log takibi: journalctl -u mailbridge.service -f
- Dinlenen portlar: ss -tulpn | grep -E ':(993|587)'
