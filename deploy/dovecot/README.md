# Dovecot integration

Use a virtual-user backend and map each account to:

```text
/vmail/%{user | domain}/%{user | username}/Maildir
```

The Maildir and Dovecot index files must be writable by the Dovecot mail user. The bridge needs write access only to each configured account's `Maildir/new` directory. Keep IMAPS on 993 and disable plaintext IMAP.

The hardened systemd unit uses `ProtectSystem=strict`; add every configured account's `Maildir/new` path to `ReadWritePaths`.

