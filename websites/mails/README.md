# website-mail

OpenBSD mailing list reader. Parses marc.info and serves a modern terminal-themed UI.

## Architecture

```
Client → relayd:443 (TLS) → Anubis:8923 (PoW bot protection) → mail-svc:8081 (aiohttp)
         httpd:80 (ACME challenges + HTTP→HTTPS redirect)
```

The mail-svc runs on port 8081, proxied through the existing relayd/anubis stack.

## Setup

```sh
# deploy mail-svc daemon
make deploy

# update code only
make update

# check status
doas rcctl check mailsvc
doas tail -f /var/log/daemon
```

## Files

```
mail.py              marc.info scraper: indexes, threads, stats
server.py            aiohttp server: /mails (HTML), /mails/api (JSON)
rc.d/mailsvc         OpenBSD rc.d script
Makefile             deploy targets
```

## Data Source

Uses marc.info HTML index pages — no mbox download, no CVS dependency.

Fetches current month for these lists:
- openbsd-tech
- openbsd-cvs
- openbsd-ports
- openbsd-misc
- openbsd-announce
- openbsd-security-announce
- openbsd-www

Refreshes every 10 minutes.

## UI

Terminal-themed (VT323 + Share Tech Mono), same aesthetic as the main site.

Three views:
- **FEED** — flat message list with filters by list, click to open on marc.info
- **THREADS** — grouped by subject, expandable
- **STATS** — top authors, daily activity, per-list breakdown
