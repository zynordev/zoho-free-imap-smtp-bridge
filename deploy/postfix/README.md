# Postfix integration

Keep port 25 disabled for this architecture. Authenticated Thunderbird submissions use port 587 and must be sent to the `mailbridge` pipe transport.

Create a transport map containing:

```text
# Local system notifications (cron, sudo, logwatch) must not reach Zoho.
root@example.com           discard:
root@mail.example.com      discard:
root@<the machine hostname> discard:
postmaster@example.com     discard:
double-bounce@example.com  discard:
MAILER-DAEMON@example.com  discard:

* mailbridge:
```

The `discard:` lines matter. Once Postfix is installed, anything on the box that mails root — a cron job's output, a sudo alert — is picked up locally and, with a bare `* mailbridge:` map, handed to the bridge. Its sender (`root@…`) is not a configured Zoho account, so the bridge cannot send it; the message is quarantined into `outbound/failed/` and logged. Discarding them at the Postfix layer keeps that noise out of the queue entirely.

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

