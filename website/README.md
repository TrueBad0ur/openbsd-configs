# website

Personal site + DDoS defence on OpenBSD.

Domain: `オープンビーエスディー.きく.コム` (`xn--dckjf5dtd7c1a8tzcde.xn--w8je.xn--tckwe`)

## Setup

```sh
# deploy httpd + get TLS cert + setup cron
make deploy

# renew cert manually
make cert

# deploy pf rules
make ddos
```

## Files

```
httpd.conf              final config: HTTP → HTTPS redirect + TLS on 443
httpd-bootstrap.conf    bootstrap config: HTTP only (used during cert request)
acme-client.conf        letsencrypt config for the domain
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
