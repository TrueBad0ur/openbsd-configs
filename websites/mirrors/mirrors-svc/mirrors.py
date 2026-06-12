import urllib.request
import urllib.parse
import socket
import concurrent.futures
import time

MIRRORS_URL = "https://www.openbsd.org/build/mirrors.dat"
TIMEOUT = 5

TLD_COUNTRY = {"bg": "Bulgaria", "br": "Brazil", "cr": "Costa Rica"}


def parse_mirrors(data):
    mirrors, current = [], {}
    for line in data.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if line == "0":
            if current:
                mirrors.append(current.copy())
            current = {}
            continue
        if "\t" not in line:
            continue
        k, _, v = line.partition("\t")
        current[k.strip()] = v.strip()
    if current:
        mirrors.append(current)
    return mirrors


def resolve_country(mirror, host=""):
    gc = mirror.get("GC", "")
    if gc and gc != "?":
        return gc
    tld = host.rsplit(".", 1)[-1].lower() if host else ""
    return TLD_COUNTRY.get(tld, "??")


def expand_cvs(mirror):
    host    = mirror.get("AH", "")
    root    = mirror.get("AR", "/cvs")
    user    = mirror.get("AU", "anoncvs")
    country = resolve_country(mirror, host)
    ap_raw  = mirror.get("AP", "")
    if not host or not ap_raw:
        return []
    entries = []
    for token in [t.strip() for t in ap_raw.split(",")]:
        if token == "ssh":
            entries.append(dict(kind="cvs", host=host, port=22, proto="ssh",
                                ssh_port=None, root=root, user=user, country=country))
        elif token == "pserver":
            entries.append(dict(kind="cvs", host=host, port=2401, proto="pserver",
                                ssh_port=None, root=root, user=user, country=country))
        elif token.startswith("ssh port "):
            p = int(token.split()[-1])
            entries.append(dict(kind="cvs", host=host, port=p, proto="ssh",
                                ssh_port=p, root=root, user=user, country=country))
    return entries


def expand_binary(mirror):
    entries, seen = [], set()
    for key, proto, port in [("UHS", "https", 443), ("UH", "http", 80), ("UF", "ftp", 21)]:
        url = mirror.get(key, "")
        if not url:
            continue
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname
            p = parsed.port or port
        except Exception:
            continue
        if not host or (host, proto) in seen:
            continue
        seen.add((host, proto))
        entries.append(dict(kind="binary", host=host, port=p, proto=proto,
                            url=url, country=resolve_country(mirror, host)))
    return entries


def check_entry(entry):
    host, port, proto = entry["host"], entry["port"], entry["proto"]
    try:
        t0 = time.monotonic()
        sock = socket.create_connection((host, port), timeout=TIMEOUT)
        if proto == "ssh":
            sock.settimeout(TIMEOUT)
            banner = sock.recv(256)
            sock.close()
            if not banner.startswith(b"SSH-"):
                return None
        else:
            sock.close()
        ms = int((time.monotonic() - t0) * 1000)
        return {**entry, "ms": ms}
    except Exception:
        return None


def fmt_cvs_cmd(m):
    WRAPPER = "/tmp/cvs_ssh_wrapper"
    if m["proto"] == "pserver":
        return "cvs -qd :pserver:" + m["user"] + "@" + m["host"] + ":" + m["root"]
    if m["ssh_port"]:
        return (
            "printf '#!/bin/sh\\nexec ssh -p " + str(m["ssh_port"]) + r' "$@"' + "\\n'"
            + " > " + WRAPPER + " && chmod +x " + WRAPPER
            + " && CVS_RSH=" + WRAPPER
            + " cvs -qd " + m["user"] + "@" + m["host"] + ":" + m["root"]
        )
    return "CVS_RSH=ssh cvs -qd " + m["user"] + "@" + m["host"] + ":" + m["root"]


def check():
    with urllib.request.urlopen(MIRRORS_URL, timeout=10) as r:
        data = r.read().decode("utf-8", errors="replace")

    mirrors = parse_mirrors(data)
    all_entries = []
    seen_binary = set()
    for m in mirrors:
        for e in expand_cvs(m):
            all_entries.append(e)
        for e in expand_binary(m):
            k = (e["host"], e["proto"])
            if k not in seen_binary:
                seen_binary.add(k)
                all_entries.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(check_entry, all_entries))

    live = [r for r in results if r]
    live_hosts = {(e["kind"], e["host"]) for e in live}
    dead_by_host = {}
    for i, r in enumerate(results):
        if not r:
            e = all_entries[i]
            k = (e["kind"], e["host"])
            if k not in live_hosts and k not in dead_by_host:
                dead_by_host[k] = e

    cvs_live   = sorted([r for r in live if r["kind"] == "cvs"],    key=lambda x: x["ms"])
    bin_live   = sorted([r for r in live if r["kind"] == "binary"], key=lambda x: x["ms"])
    cvs_dead   = [v for k, v in dead_by_host.items() if k[0] == "cvs"]
    bin_dead   = [v for k, v in dead_by_host.items() if k[0] == "binary"]

    # Group binary by host
    bin_by_host = {}
    for m in bin_live:
        h = m["host"]
        if h not in bin_by_host:
            bin_by_host[h] = {"country": m["country"], "ms": m["ms"],
                              "protos": [], "best_url": m["url"]}
        bin_by_host[h]["protos"].append(m["proto"])
        if m["ms"] < bin_by_host[h]["ms"]:
            bin_by_host[h]["ms"] = m["ms"]
            bin_by_host[h]["best_url"] = m["url"]
    bin_grouped = [{"host": h, **info} for h, info in
                   sorted(bin_by_host.items(), key=lambda x: x[1]["ms"])]

    cvs_cmds = []
    if cvs_live:
        cvs_cmds.append(fmt_cvs_cmd(cvs_live[0]) + " update -rOPENBSD_7_9 -Pd src ports")
    for alt_port in (443, 2022):
        alt = next((m for m in cvs_live if m.get("ssh_port") == alt_port), None)
        if alt:
            cvs_cmds.append("port " + str(alt_port) + ": " + fmt_cvs_cmd(alt) + " update -rOPENBSD_7_9 -Pd src ports")

    return {
        "binaries":    bin_grouped,
        "binary_dead": [{"host": m.get("host"), "country": m.get("country")} for m in bin_dead],
        "cvs":         cvs_live,
        "cvs_dead":    [{"host": m.get("host"), "country": m.get("country")} for m in cvs_dead],
        "cvs_cmds":    cvs_cmds,
    }
