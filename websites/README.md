# websites

Unified web stack for [オープンビーエスディー.きく.コム](https://xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe) running on OpenBSD (openbsd.amsterdam VPS).

**IP:** `46.23.92.46`  
**Punycode:** `xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe`

## Architecture

```
Internet → relayd:443 (TLS) → Anubis:8923 (PoW bot filter) → websvc:8080 (aiohttp)
                                                                  ├── /mirrors  (mirror status)
                                                                  └── /mails    (mailing lists)

SMTP:25 → smtpd → processor.py (_mailproc) → /var/db/mails/mails.db (SQLite)
                                                        ↑
                                                   websvc reads this
```

## Deploy

```sh
cd websites
make deploy   # full deploy (httpd + anubis + relayd + websvc)
make update   # code only (restarts websvc)
make ddos     # update pf rules
```

## DNS records required

| Type | Name | Value |
|------|------|-------|
| A | `xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe` | `46.23.92.46` |
| MX | `xn--w8je.xn--tckwe` (or subdomain) | `xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe` priority 10 |
| TXT | `xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe` | `v=spf1 ip4:46.23.92.46 -all` |

### PTR (reverse DNS)

Set via openbsd.amsterdam PTR daemon **from within the VM**:

```sh
TOKEN=$(ftp -MVo- http://ptr4.openbsd.amsterdam/token | tr -d '\r\n')
ftp -MVo- "http://ptr4.openbsd.amsterdam/${TOKEN}/xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe"
```

> **Note:** As of 2026-06 the daemon rejects punycode (xn--) hostnames with 400.  
> Workaround: contact openbsd.amsterdam support to set PTR manually, or subscribe to mailing lists from a personal email (see below).

## Mailing list subscription

Because outbound mail from our server is blocked by mail.openbsd.org (PTR mismatch), subscriptions must be done from a personal email account.

**Step 1** — Send from personal Gmail to `majordomo@openbsd.org` (plain text, no HTML):

```
subscribe tech lists@xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe
subscribe misc lists@xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe
subscribe ports lists@xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe
subscribe announce lists@xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe
subscribe www lists@xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe
```

> In Gmail: before sending click the A̲ icon → "Plain text" to disable HTML, otherwise Gmail wraps long punycode addresses with `=` (quoted-printable) and majordomo rejects them.

**Step 2** — Confirmations arrive at our server and are saved to `/var/db/mails/majordomo.log`. Read them:

```sh
doas cat /var/db/mails/majordomo.log
```

Each confirmation contains an auth command like:

```
auth XXXXXXXXXXXXXXXX subscribe tech lists@xn--...
```

**Step 3** — Send that auth command from personal Gmail to `majordomo@openbsd.org` (plain text, one line per list).

**Step 4** — Done. List mail starts flowing into `/var/db/mails/mails.db` and appears at `/mails`.

### Unsubscribe

```
unsubscribe tech lists@xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe
```

## Files

```
websites/
├── Makefile                    # top-level deploy
├── root/
│   └── assets/                 # main landing page (HTML/CSS/JS)
├── shared/
│   ├── server.py               # unified aiohttp service (port 8080)
│   └── rc.d/websvc             # rc.d daemon script (_websvc user)
├── mirrors/
│   ├── assets/                 # mirrors frontend (HTML/CSS/JS)
│   ├── httpd.conf              # ACME + HTTP→HTTPS redirect
│   ├── relayd.conf             # TLS termination
│   ├── acme-client.conf        # Let's Encrypt
│   ├── anubis.env              # PoW config
│   ├── mirrors-svc/mirrors.py  # mirror checker
│   └── ddos_defence/
│       ├── pf.conf             # firewall rules
│       └── Makefile
└── mails/
    ├── mail.py                 # SQLite reader (served via websvc)
    ├── processor.py            # smtpd MDA: parses email → SQLite
    ├── smtpd.conf              # receive external mail on port 25
    └── assets/                 # frontend (HTML/CSS/JS)
```

## Runtime paths on server

| Path | Description |
|------|-------------|
| `/home/scripts/website-svc/` | websvc code (server.py, mail.py, mirrors.py, assets/) |
| `/home/scripts/mailproc/processor.py` | smtpd MDA script |
| `/var/db/mails/mails.db` | SQLite mail database |
| `/var/db/mails/majordomo.log` | majordomo confirmations log |
| `/etc/rc.d/websvc` | daemon script |

## Users

| User | Purpose |
|------|---------|
| `_websvc` | runs websvc (aiohttp), reads DB read-only |
| `_mailproc` | runs processor.py via smtpd MDA, writes to DB |

## pf whitelist

To never block an IP (e.g. your home IP):

```sh
doas pfctl -t whitelist -T add YOUR_IP
```

To make permanent, add to `mirrors/ddos_defence/pf.conf`:

```
table <whitelist> persist { YOUR_IP }
```

The repo has `YOU_IP_ADDRESS` as placeholder — replace before deploying pf rules.

## Cert renewal

Handled by cron (set by `make relayd`):

```
0 0 * * * acme-client openbsd-kiku && cat /etc/ssl/openbsd-kiku.crt /etc/ssl/openbsd-kiku-chain.crt > /etc/ssl/0.0.0.0:443.crt && rcctl reload relayd
```
