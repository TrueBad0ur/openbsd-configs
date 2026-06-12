#!/usr/bin/env python3
"""
mirrors-svc: serves OpenBSD mirror status at /servers (dynamic)
and static files from STATIC_ROOT for all other paths.
Add new pages: append to REGISTRY.
"""

import asyncio
import concurrent.futures
import concurrent.futures.thread
import concurrent.futures.process
import ctypes
import ctypes.util
import encodings.ascii
import encodings.idna
import encodings.latin_1
import encodings.utf_8
import http.client
import mimetypes
import os
import platform
import sys
import time
import logging
from pathlib import Path
from aiohttp import web
import aiohttp.web_fileresponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mirrors as mirrors_checker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def harden():
    """Apply pledge + unveil on OpenBSD. No-op on other systems."""
    if platform.system() != "OpenBSD":
        return
    # warm up ThreadPoolExecutor lazy init before locking down FS
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    pool.shutdown(wait=False)

    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

    libc.unveil(str(STATIC_ROOT).encode(), b"r")
    libc.unveil(b"/etc/ssl/cert.pem", b"r")
    libc.unveil(None, None)

    r = libc.pledge(b"stdio inet dns rpath", None)
    if r != 0:
        raise OSError(ctypes.get_errno(), "pledge failed")
log = logging.getLogger(__name__)

HOST        = "127.0.0.1"
PORT        = 8080
INTERVAL    = 300   # seconds between mirror checks
STATIC_ROOT = Path("/var/www/htdocs")

# --- Registry: (url_path, checker_module, page_title) ---
REGISTRY = [
    ("/servers", mirrors_checker, "OpenBSD Mirror Status"),
]

state = {path: {"data": None, "last_updated": 0.0, "next_update": 0.0}
         for path, _, _ in REGISTRY}

DYNAMIC_PATHS = {p for p, _, _ in REGISTRY}


# --- Background checkers ---

async def checker_loop(path, checker, interval):
    while True:
        t0 = time.monotonic()
        try:
            log.info("checking %s ...", path)
            data = await asyncio.get_event_loop().run_in_executor(None, checker.check)
            now = time.time()
            state[path].update(data=data, last_updated=now, next_update=now + interval)
            log.info("done %s in %.1fs", path, time.monotonic() - t0)
        except Exception as e:
            log.error("check failed for %s: %s", path, e)
        await asyncio.sleep(interval)


# --- API handler (one per registered path) ---

def make_api_handler(path):
    async def handler(request):
        s = state[path]
        if s["data"] is None:
            return web.json_response({"status": "checking"}, status=503)
        return web.json_response({
            "last_updated": s["last_updated"],
            "next_update":  s["next_update"],
            "data":         s["data"],
        })
    return handler


# --- HTML page shell (JS fetches data from API) ---

def render_page(title, api_path):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=VT323&display=swap');
  :root {{ --green:#00ff41; --green-dim:#00aa2a; --bg:#0a0a0a; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--green); font-family:'Share Tech Mono',monospace; min-height:100vh; }}
  body::before {{
    content:''; position:fixed; inset:0;
    background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.08) 2px,rgba(0,0,0,.08) 4px);
    pointer-events:none; z-index:100;
  }}
  .terminal {{ max-width:960px; margin:0 auto; padding:60px 24px 80px; }}
  .term-header {{ display:flex; align-items:center; gap:8px; margin-bottom:40px; padding-bottom:16px; border-bottom:1px solid #1a1a1a; }}
  .dot {{ width:12px; height:12px; border-radius:50%; }}
  .dot-r {{ background:#ff5f57; box-shadow:0 0 6px #ff5f57; }}
  .dot-y {{ background:#ffbd2e; box-shadow:0 0 6px #ffbd2e; }}
  .dot-g {{ background:#28c840; box-shadow:0 0 6px #28c840; }}
  .back {{ font-size:13px; color:var(--green-dim); text-decoration:none; margin-left:auto; }}
  .back:hover {{ color:var(--green); }}
  h2 {{ font-family:'VT323',monospace; font-size:32px; color:var(--green); letter-spacing:2px; margin-bottom:6px; }}
  .section {{ margin-bottom:48px; }}
  .cmd-block {{ margin-bottom:16px; }}
  .cmd-line {{ font-size:12px; color:var(--green-dim); padding:6px 12px; background:#0d0d0d; border-left:2px solid var(--green-dim); margin-bottom:4px; word-break:break-all; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; font-size:10px; color:#444; letter-spacing:3px; text-transform:uppercase; padding:8px 10px 8px 0; border-bottom:1px solid #1c1c1c; }}
  td {{ padding:6px 10px 6px 0; border-bottom:1px solid #111; vertical-align:middle; }}
  .ok {{ color:var(--green); }} .dead {{ color:#444; }}
  .dot-ok  {{ color:#00ff41; text-shadow:0 0 6px #00ff41; font-size:10px; }}
  .dot-dead {{ color:#ff4444; text-shadow:0 0 4px #ff4444; font-size:10px; }}
  .protos {{ color:#00aa2a; font-size:12px; }}
  .dead .protos {{ color:#333; }}
  .ms {{ color:#007a1f; font-size:12px; white-space:nowrap; }}
  .dead .ms {{ color:#333; }}
  .spinner {{ color:#555; font-size:13px; margin:40px 0; }}
  .status-line {{ position:fixed; bottom:0; left:0; right:0; padding:6px 24px; background:#080808; border-top:1px solid #1a1a1a; display:flex; justify-content:space-between; font-size:11px; color:#333; z-index:50; letter-spacing:1px; }}
  .status-line span {{ color:var(--green-dim); }}
  .ts {{ color:#555; }}
</style>
</head>
<body>
<div class="terminal">
  <div class="term-header">
    <div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div>
    <span style="font-size:12px;color:#444;margin-left:8px;letter-spacing:2px;">truebad0ur@openbsd ~ — ssh</span>
    <a class="back" href="/">← back</a>
  </div>
  <div id="content"><p class="spinner">fetching data...</p></div>
</div>
<div class="status-line">
  <span>OpenBSD 7.9 · aiohttp</span>
  <span class="ts" id="ts">—</span>
</div>
<script>
const API = '{api_path}';
let _nextFetch = null;

function esc(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

function startTimer(lastUpdated, nextUpdate) {{
  if (window._timer) clearInterval(window._timer);
  const updStr = new Date(lastUpdated*1000).toISOString().replace('T',' ').slice(0,16)+' UTC';
  window._timer = setInterval(() => {{
    const secs = Math.max(0, Math.round((nextUpdate*1000 - Date.now())/1000));
    const m = Math.floor(secs/60), s = secs%60;
    document.getElementById('ts').textContent =
      'updated: '+updStr+'  ·  refresh in '+(secs>0 ? m+':'+String(s).padStart(2,'0') : 'updating...');
  }}, 1000);
}}

function render(d) {{
  const binRows = d.binaries.map(m=>
    `<tr class="ok"><td><span class="dot-ok">●</span></td><td>${{esc(m.country)}}</td><td class="protos">${{esc(m.protos.join(' '))}}</td><td>${{esc(m.host)}}</td><td class="ms">${{m.ms}}ms</td></tr>`
  ).join('')+d.binary_dead.map(m=>
    `<tr class="dead"><td><span class="dot-dead">●</span></td><td>${{esc(m.country)}}</td><td></td><td>${{esc(m.host)}}</td><td></td></tr>`
  ).join('');
  const cvsRows = d.cvs.map(m=>{{
    const p=(m.port!==22&&m.port!==2401)?':'+m.port:'';
    return `<tr class="ok"><td><span class="dot-ok">●</span></td><td>${{esc(m.country)}}</td><td class="protos">${{esc(m.proto+p)}}</td><td>${{esc(m.host)}}</td><td class="ms">${{m.ms}}ms</td></tr>`;
  }}).join('')+d.cvs_dead.map(m=>
    `<tr class="dead"><td><span class="dot-dead">●</span></td><td>${{esc(m.country)}}</td><td></td><td>${{esc(m.host)}}</td><td></td></tr>`
  ).join('');
  const cmds = d.cvs_cmds.map(c=>`<div class="cmd-line">$ ${{esc(c)}}</div>`).join('');
  const pkg = d.binaries[0]?d.binaries[0].best_url:'';
  document.getElementById('content').innerHTML=
    `<div class="section"><h2>BINARIES</h2>
    <p style="font-size:11px;color:#444;margin-bottom:14px;letter-spacing:1px;">pkg_add · iso · firmware</p>
    <div class="cmd-block"><div class="cmd-line">$ PKG_PATH=${{esc(pkg)}} pkg_add &lt;package&gt;</div></div>
    <table><thead><tr><th></th><th>country</th><th>proto</th><th>host</th><th>ms</th></tr></thead><tbody>${{binRows}}</tbody></table></div>
    <div class="section"><h2>CVS (anoncvs)</h2>
    <p style="font-size:11px;color:#444;margin-bottom:14px;letter-spacing:1px;">src · ports · xenocara</p>
    <div class="cmd-block">${{cmds}}</div>
    <table><thead><tr><th></th><th>country</th><th>proto</th><th>host</th><th>ms</th></tr></thead><tbody>${{cvsRows}}</tbody></table></div>`;
}}

async function fetchData() {{
  if (_nextFetch) clearTimeout(_nextFetch);
  try {{
    const r = await fetch(API);
    if (r.status===503) {{
      document.getElementById('ts').textContent='checking servers...';
      _nextFetch=setTimeout(fetchData,3000); return;
    }}
    const j = await r.json();
    render(j.data);
    startTimer(j.last_updated, j.next_update);
    _nextFetch=setTimeout(fetchData, Math.max(5000, j.next_update*1000-Date.now()+3000));
  }} catch(e) {{
    document.getElementById('ts').textContent='error: '+e.message;
    _nextFetch=setTimeout(fetchData,10000);
  }}
}}

fetchData();
</script>
</body>
</html>"""


def make_page_handler(title, api_path):
    async def handler(request):
        return web.Response(text=render_page(title, api_path), content_type="text/html")
    return handler


# --- Static file handler ---

async def static_handler(request):
    rel = request.path.lstrip("/") or "index.html"
    path = STATIC_ROOT / rel
    if path.is_dir():
        path = path / "index.html"
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound()
    mime, _ = mimetypes.guess_type(str(path))
    return web.FileResponse(path, headers={"Content-Type": mime or "application/octet-stream"})


# --- App wiring ---

async def on_startup(app):
    app["tasks"] = []
    for path, checker, _ in REGISTRY:
        task = asyncio.create_task(checker_loop(path, checker, INTERVAL))
        app["tasks"].append(task)
    harden()
    log.info("process hardened (pledge+unveil)")


async def on_cleanup(app):
    for t in app["tasks"]:
        t.cancel()


def make_app():
    app = web.Application()
    for path, _, title in REGISTRY:
        api_path = path + "/api"
        app.router.add_get(path,       make_page_handler(title, api_path))
        app.router.add_get(path + "/", make_page_handler(title, api_path))
        app.router.add_get(api_path,   make_api_handler(path))
    app.router.add_get("/{tail:.*}", static_handler)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    app = make_app()
    web.run_app(app, host=HOST, port=PORT, access_log=log)
