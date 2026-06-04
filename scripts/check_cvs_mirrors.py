#!/usr/bin/env python3
"""Check all OpenBSD mirrors: CVS (anoncvs) and binary (http/ftp)"""

import urllib.request
import urllib.parse
import socket
import concurrent.futures
import sys
import time

MIRRORS_URL = "https://www.openbsd.org/build/mirrors.dat"
TIMEOUT = 5
WRAPPER_PATH = "/tmp/cvs_ssh_wrapper"


def parse_mirrors(data):
    mirrors = []
    current = {}
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


TLD_COUNTRY = {
    "bg": "Bulgaria", "br": "Brazil", "cr": "Costa Rica",
}


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
    country = None
    entries = []
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
        if not host:
            continue
        entries.append(dict(kind="binary", host=host, port=p, proto=proto,
                            url=url, country=resolve_country(mirror, host)))
    return entries


def check_entry(entry):
    host  = entry["host"]
    port  = entry["port"]
    proto = entry["proto"]
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
    if m["proto"] == "pserver":
        return "cvs -qd :pserver:" + m["user"] + "@" + m["host"] + ":" + m["root"]
    if m["ssh_port"]:
        return (
            "printf '#!/bin/sh\\nexec ssh -p " + str(m["ssh_port"]) + r' "$@"' + "\\n'"
            + " > " + WRAPPER_PATH + " && chmod +x " + WRAPPER_PATH
            + " && CVS_RSH=" + WRAPPER_PATH
            + " cvs -qd " + m["user"] + "@" + m["host"] + ":" + m["root"]
        )
    return "CVS_RSH=ssh cvs -qd " + m["user"] + "@" + m["host"] + ":" + m["root"]


def main():
    print("Fetching mirrors.dat ...", flush=True)
    try:
        with urllib.request.urlopen(MIRRORS_URL, timeout=10) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("error: " + str(e), file=sys.stderr)
        sys.exit(1)

    mirrors = parse_mirrors(data)

    # Expand: prefer one binary entry per mirror (best proto), all cvs variants
    all_entries = []
    seen_binary_host = set()
    for m in mirrors:
        for e in expand_cvs(m):
            all_entries.append(e)
        for e in expand_binary(m):
            key = (e["host"], e["proto"])
            if key not in seen_binary_host:
                seen_binary_host.add(key)
                all_entries.append(e)

    print("Checking " + str(len(all_entries)) + " endpoints (timeout=" + str(TIMEOUT) + "s) ...\n", flush=True)

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

    # Group binary live results by host
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
    bin_grouped = sorted(bin_by_host.items(), key=lambda x: x[1]["ms"])

    # --- BINARIES ---
    print("=" * 110)
    print("BINARIES")
    if bin_grouped:
        best_url = bin_grouped[0][1]["best_url"]
        print("  PKG_PATH=" + best_url + " pkg_add <package>")
    print("=" * 110)
    print("{:<4}  {:<16} {:<16} {:<45} {:>5}".format("", "COUNTRY", "PROTO", "HOST", "MS"))
    print("-" * 85)
    for host, info in bin_grouped:
        protos = " ".join(info["protos"])
        print("{:<4}  {:<16} {:<16} {:<45} {:>4}ms".format(
            "ok", info["country"], protos, host, info["ms"]))
    for m in bin_dead:
        print("{:<4}  {:<16} {}".format("dead", m.get("country", "??"), m.get("host", "?")))

    print("\n" + str(len(bin_live)) + " live, " + str(len(bin_dead)) + " unreachable\n")

    # --- CVS ---
    print("=" * 110)
    print("CVS (anoncvs)")
    if cvs_live:
        best = cvs_live[0]
        print("  " + fmt_cvs_cmd(best) + " update -rOPENBSD_7_9 -Pd src ports")
    for alt_port in (443, 2022):
        alt = next((m for m in cvs_live if m.get("ssh_port") == alt_port), None)
        if alt:
            print("  port " + str(alt_port) + ": " + fmt_cvs_cmd(alt) + " update -rOPENBSD_7_9 -Pd src ports")
    print("=" * 110)
    print("{:<4}  {:<16} {:<9} {:<45} {:>5}".format("", "COUNTRY", "PROTO", "HOST", "MS"))
    print("-" * 80)
    for m in cvs_live:
        port_label = ":" + str(m["port"]) if m["port"] not in (22, 2401) else ""
        print("{:<4}  {:<16} {:<9} {:<45} {:>4}ms".format(
            "ok", m["country"], m["proto"] + port_label, m["host"], m["ms"]))
    for m in cvs_dead:
        print("{:<4}  {:<16} {}".format("dead", m.get("country", "??"), m.get("host", "?")))

    print("\n" + str(len(cvs_live)) + " live, " + str(len(cvs_dead)) + " unreachable")


if __name__ == "__main__":
    main()
