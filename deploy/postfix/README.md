# Postfix integration

Keep port 25 disabled for this architecture. Authenticated Thunderbird submissions use port 587 and must be sent to the `mailbridge` pipe transport.

Create a transport map containing:

```text
* mailbridge:
```

Install `deploy/mailbridge-submit` as `/usr/local/sbin/mailbridge-submit`, then define the pipe transport in `master.cf`:

```text
mailbridge unix - n n - - pipe
  flags= user=mailbridge argv=/usr/local/sbin/mailbridge-submit --sender=${sender} --recipients=${recipient}
```

The `user=mailbridge` clause is required: `install.sh` creates `/var/spool/mailbridge/outbound` owned by the `mailbridge` user, and only its owner has write access to that directory. If the pipe runs as a different user, `mailbridge-submit` cannot even create the queued file there (permission denied), so submissions will fail outright.

Create `/etc/postfix/sender_login_maps` with one allowed sender per line, e.g.:

```text
person@example.com person@example.com
```

map it with `postmap /etc/postfix/sender_login_maps`, reference it from `smtpd_sender_login_maps` in `main.cf`, and enforce `smtpd_sender_restrictions = reject_sender_login_mismatch, ...`. The submission service must require TLS and SASL authentication and reject unauthenticated recipients.

Do not leave normal Internet delivery enabled for bridge mail, otherwise duplicate or direct deliveries can occur.

