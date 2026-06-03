# website

Personal site + DDoS defence on OpenBSD.

Domain: `オープンビーエスディー.きく.コム` (`xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe`)

## Architecture

```
Client → relayd:443 (TLS) → Anubis:8923 (PoW bot protection) → httpd:8080 (static files)
         httpd:80 (ACME challenges + HTTP→HTTPS redirect)
```

## Setup

```sh
# full deploy: httpd + cert + anubis + relayd + cron
make deploy

# deploy/update anubis + relayd only
make anubis

# renew cert manually
make cert

# deploy pf rules
make ddos
```

## Files

```
httpd.conf              backend: internal 127.0.0.1:8080 + port 80 ACME/redirect
httpd-bootstrap.conf    bootstrap: HTTP only (used during initial cert request)
acme-client.conf        letsencrypt config
relayd.conf             TLS termination on 443 → Anubis:8923
anubis.env              Anubis config (bind, target, difficulty, cookie domain)
index.html              landing page
ddos_defence/           pf rate limiting rules + monitoring tools
```

---

# ddos_defence

OpenBSD `pf` protection against HTTP flood and SSH bruteforce.

## Setup

```sh
# deploy pf.conf
make deploy

# install monitoring tools (netplot, ttyplot, fzf, pcre)
make tools
```

## pf rules summary

| Rule | Limit |
|------|-------|
| SSH | max 5 concurrent, 3 new/10s → `<bruteforce>` |
| HTTP/HTTPS | max 100 concurrent, 15 new/5s → `<ddos>` |

IPs in tables are blocked permanently until manual flush.

## Monitoring

```sh
# show blocked IPs
pfctl -t ddos -T show
pfctl -t bruteforce -T show

# flush tables
pfctl -t ddos -T flush
pfctl -t bruteforce -T flush

# pf stats
pfctl -s info

# live traffic graph
~/.local/bin/netplot vio0

# pf rules
pfctl -s rules
```

## Test

```sh
# from another server
pip install aiohttp
python3 flood.py https://target-domain
```
