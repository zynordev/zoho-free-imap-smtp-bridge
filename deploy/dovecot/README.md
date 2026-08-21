# Dovecot integration

Use a virtual-user backend and map each account to:

```text
mail_location = maildir:/vmail/%{user | domain}/%{user | username}/Maildir
```

This must be plain Maildir++ layout (Dovecot's default for `maildir:` — do not set `LAYOUT=fs`). The bridge auto-discovers every Zoho folder (Sent, Drafts, Trash, Spam, any custom folder) per account and creates a matching `.FolderName` subfolder under `Maildir` on demand, using Maildir++'s dot-prefixed naming. With `LAYOUT=fs` those subfolders would need a different directory shape and would not show up in Thunderbird.

The Maildir and Dovecot index files must be writable by the Dovecot mail user. The bridge needs write access to each configured account's whole `Maildir` tree (not just `Maildir/new`), since it creates new subfolders there as Zoho's folder list changes. Keep IMAPS on 993 and disable plaintext IMAP.

The hardened systemd unit uses `ProtectSystem=strict`; add every configured account's `Maildir` path (the whole tree) to `ReadWritePaths`.

