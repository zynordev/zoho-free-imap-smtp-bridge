# Postfix integration

Keep port 25 disabled for this architecture. Authenticated Thunderbird submissions use port 587 and must be sent to the `mailbridge` pipe transport.

Create a transport map containing:

```text
* mailbridge:
```

Create `/etc/postfix/sender_login_maps` with one allowed sender per line, map it with `postmap`, and enforce `reject_sender_login_mismatch`. The submission service must require TLS and SASL authentication and reject unauthenticated recipients.

Install `deploy/mailbridge-submit` as `/usr/local/sbin/mailbridge-submit`. Do not leave normal Internet delivery enabled for bridge mail, otherwise duplicate or direct deliveries can occur.

