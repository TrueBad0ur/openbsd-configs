#!/usr/bin/env python3
"""Generate /var/www/htdocs/servers.html — OpenBSD mirror status page."""

import os
import urllib.request
import urllib.parse
import socket
import concurrent.futures
import sys
import time
from datetime import datetime, timezone

MIRRORS_URL  = "https://www.openbsd.org/build/mirrors.dat"
OUTPUT_PATH  = "/var/www/htdocs/servers/index.html"
TIMEOUT      = 5
WRAPPER_PATH = "/tmp/cvs_ssh_wrapper"

TLD_COUNTRY = {
    "bg": "Bulgaria", "br": "Brazil", "cr": "Costa Rica",
}


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
    entries = []
    seen = set()
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


def h(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_html(bin_grouped, bin_dead, cvs_live, cvs_dead, cvs_cmds, ts):
    rows_bin = ""
    for host, info in bin_grouped:
        protos = " ".join(info["protos"])
        rows_bin += (
            f'<tr class="ok">'
            f'<td><span class="dot dot-ok">●</span></td>'
            f'<td>{h(info["country"])}</td>'
            f'<td class="protos">{h(protos)}</td>'
            f'<td class="host">{h(host)}</td>'
            f'<td class="ms">{info["ms"]}ms</td>'
            f'</tr>\n'
        )
    for m in bin_dead:
        rows_bin += (
            f'<tr class="dead">'
            f'<td><span class="dot dot-dead">●</span></td>'
            f'<td>{h(m.get("country","??"))}</td>'
            f'<td></td>'
            f'<td class="host">{h(m.get("host","?"))}</td>'
            f'<td></td>'
            f'</tr>\n'
        )

    rows_cvs = ""
    for m in cvs_live:
        port_label = (":" + str(m["port"])) if m["port"] not in (22, 2401) else ""
        rows_cvs += (
            f'<tr class="ok">'
            f'<td><span class="dot dot-ok">●</span></td>'
            f'<td>{h(m["country"])}</td>'
            f'<td class="protos">{h(m["proto"] + port_label)}</td>'
            f'<td class="host">{h(m["host"])}</td>'
            f'<td class="ms">{m["ms"]}ms</td>'
            f'</tr>\n'
        )
    for m in cvs_dead:
        rows_cvs += (
            f'<tr class="dead">'
            f'<td><span class="dot dot-dead">●</span></td>'
            f'<td>{h(m.get("country","??"))}</td>'
            f'<td></td>'
            f'<td class="host">{h(m.get("host","?"))}</td>'
            f'<td></td>'
            f'</tr>\n'
        )

    cmd_lines = "".join(f'<div class="cmd-line">$ {h(c)}</div>' for c in cvs_cmds)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>openbsd mirror status</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=VT323&display=swap');
  :root {{
    --green: #00ff41;
    --green-dim: #00aa2a;
    --green-glow: rgba(0,255,65,0.15);
    --red: #ff4444;
    --bg: #0a0a0a;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: var(--bg);
    color: var(--green);
    font-family: 'Share Tech Mono', monospace;
    min-height: 100vh;
  }}
  body::before {{
    content:''; position:fixed; top:0; left:0; width:100%; height:100%;
    background: repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.08) 2px,rgba(0,0,0,0.08) 4px);
    pointer-events:none; z-index:100;
  }}
  .terminal {{ max-width:960px; margin:0 auto; padding:60px 24px 80px; }}
  .term-header {{
    display:flex; align-items:center; gap:8px;
    margin-bottom:40px; padding-bottom:16px; border-bottom:1px solid #1a1a1a;
  }}
  .dot {{ width:12px; height:12px; border-radius:50%; }}
  .dot-r {{ background:#ff5f57; box-shadow:0 0 6px #ff5f57; }}
  .dot-y {{ background:#ffbd2e; box-shadow:0 0 6px #ffbd2e; }}
  .dot-g {{ background:#28c840; box-shadow:0 0 6px #28c840; }}
  .back {{ font-size:13px; color:var(--green-dim); text-decoration:none; }}
  .back:hover {{ color:var(--green); }}
  h2 {{
    font-family:'VT323', monospace; font-size:32px;
    color:var(--green); letter-spacing:2px; margin-bottom:6px;
  }}
  .section {{ margin-bottom:48px; }}
  .cmd-block {{ margin-bottom:16px; }}
  .cmd-line {{
    font-size:12px; color:var(--green-dim);
    padding:6px 12px; background:#0d0d0d;
    border-left:2px solid var(--green-dim);
    margin-bottom:4px; word-break:break-all;
  }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{
    text-align:left; font-size:10px; color:#444;
    letter-spacing:3px; text-transform:uppercase;
    padding:8px 10px 8px 0; border-bottom:1px solid #1c1c1c;
  }}
  td {{ padding:6px 10px 6px 0; border-bottom:1px solid #111; vertical-align:middle; }}
  tr.ok td {{ color:var(--green); }}
  tr.dead td {{ color:#444; }}
  .dot-ok  {{ color:#00ff41; text-shadow:0 0 6px #00ff41; font-size:10px; }}
  .dot-dead {{ color:#ff4444; text-shadow:0 0 4px #ff4444; font-size:10px; }}
  .protos {{ color:#00aa2a; font-size:12px; }}
  tr.dead .protos {{ color:#333; }}
  .host {{ font-size:13px; }}
  .ms {{ color:#555; font-size:12px; white-space:nowrap; }}
  tr.ok .ms {{ color:#007a1f; }}
  .status-line {{
    position:fixed; bottom:0; left:0; right:0;
    padding:6px 24px; background:#080808;
    border-top:1px solid #1a1a1a;
    display:flex; justify-content:space-between;
    font-size:11px; color:#333; z-index:50; letter-spacing:1px;
  }}
  .status-line span {{ color:var(--green-dim); }}
  .ts {{ color:#555; }}
</style>
</head>
<body>
<div class="terminal">

  <div class="term-header">
    <div class="dot dot-r"></div>
    <div class="dot dot-y"></div>
    <div class="dot dot-g"></div>
    <span style="font-size:12px;color:#444;margin-left:8px;letter-spacing:2px;">truebad0ur@openbsd ~ — ssh</span>
    <span style="flex:1"></span>
    <a class="back" href="/">← back</a>
  </div>

  <div class="section">
    <h2>BINARIES</h2>
    <p style="font-size:11px;color:#444;margin-bottom:14px;letter-spacing:1px;">pkg_add · iso · firmware</p>
    <div class="cmd-block">
      <div class="cmd-line">$ PKG_PATH={h(bin_grouped[0][1]["best_url"] if bin_grouped else "")} pkg_add &lt;package&gt;</div>
    </div>
    <table>
      <thead><tr>
        <th></th><th>country</th><th>proto</th><th>host</th><th>ms</th>
      </tr></thead>
      <tbody>{rows_bin}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>CVS (anoncvs)</h2>
    <p style="font-size:11px;color:#444;margin-bottom:14px;letter-spacing:1px;">src · ports · xenocara</p>
    <div class="cmd-block">{cmd_lines}</div>
    <table>
      <thead><tr>
        <th></th><th>country</th><th>proto</th><th>host</th><th>ms</th>
      </tr></thead>
      <tbody>{rows_cvs}</tbody>
    </table>
  </div>

</div>

<div class="status-line">
  <span>OpenBSD 7.9 · httpd(8)</span>
  <span class="ts">updated: {h(ts)} · refresh in <span id="cd">5:00</span></span>
</div>

<script>
  const el = document.getElementById('cd');
  const PERIOD   = 60000;
  const CRON_LAG = 20000;
  let reloading = false;

  function msToNext() {{ return PERIOD - (Date.now() % PERIOD); }}

  function tick() {{
    if (reloading) return;
    const ms = msToNext();
    if (ms < 1000) {{
      reloading = true;
      el.textContent = 'updating...';
      setTimeout(() => location.reload(), CRON_LAG);
      return;
    }}
    const s = Math.ceil((ms + CRON_LAG) / 1000);
    el.textContent = Math.floor(s/60) + ':' + String(s%60).padStart(2,'0');
  }}

  tick();
  setInterval(tick, 1000);

  document.addEventListener('visibilitychange', () => {{
    if (!document.hidden && msToNext() > PERIOD - 5000) location.reload();
  }});
</script>

</body>
</html>
"""


def main():
    print("Fetching mirrors.dat ...", flush=True)
    try:
        with urllib.request.urlopen(MIRRORS_URL, timeout=10) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("error: " + str(e), file=sys.stderr)
        sys.exit(1)

    mirrors = parse_mirrors(data)
    all_entries = []
    seen_binary = set()
    for m in mirrors:
        for e in expand_cvs(m):
            all_entries.append(e)
        for e in expand_binary(m):
            key = (e["host"], e["proto"])
            if key not in seen_binary:
                seen_binary.add(key)
                all_entries.append(e)

    print(f"Checking {len(all_entries)} endpoints ...", flush=True)
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

    cvs_live = sorted([r for r in live if r["kind"] == "cvs"],    key=lambda x: x["ms"])
    bin_live = sorted([r for r in live if r["kind"] == "binary"], key=lambda x: x["ms"])
    cvs_dead = [v for k, v in dead_by_host.items() if k[0] == "cvs"]
    bin_dead = [v for k, v in dead_by_host.items() if k[0] == "binary"]

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

    cvs_cmds = []
    if cvs_live:
        cvs_cmds.append(fmt_cvs_cmd(cvs_live[0]) + " update -rOPENBSD_7_9 -Pd src ports")
    for alt_port in (443, 2022):
        alt = next((m for m in cvs_live if m.get("ssh_port") == alt_port), None)
        if alt:
            cvs_cmds.append(
                f"port {alt_port}: " + fmt_cvs_cmd(alt) + " update -rOPENBSD_7_9 -Pd src ports"
            )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = build_html(bin_grouped, bin_dead, cvs_live, cvs_dead, cvs_cmds, ts)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)
    print(f"Written to {OUTPUT_PATH}  ({len(bin_grouped)} binary, {len(cvs_live)} cvs live)")


if __name__ == "__main__":
    main()
