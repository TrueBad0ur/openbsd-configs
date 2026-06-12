#!/usr/bin/env python3
"""Unified OpenBSD websites server.

Serves /mirrors (mirror status) and /mails (mailing lists) on port 8080.
Behind relayd:443 → Anubis:8923 → this service.
"""

import asyncio
import concurrent.futures
import concurrent.futures.thread
import ctypes, ctypes.util
import encodings.ascii
import encodings.idna
import encodings.latin_1
import encodings.utf_8
import http.client
import mimetypes, os, platform, sys, time, logging
from pathlib import Path
from aiohttp import web
import aiohttp.web_fileresponse

SVC_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(SVC_DIR))
import mirrors as mirrors_checker
import mail as mail_checker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8080
STATIC_ROOT = Path("/var/www/htdocs")
ASSETS_DIR = SVC_DIR / "assets"

# (path, checker, interval, title)
REGISTRY = [
    ("/mirrors", mirrors_checker, 300, "OpenBSD Mirror Status"),
    ("/mails",   mail_checker,     60, "OpenBSD Mailing Lists"),
]

state = {p: {"data": None, "last_updated": 0.0, "next_update": 0.0} for p, _, _, _ in REGISTRY}


def harden():
    if platform.system() != "OpenBSD":
        return
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    pool.shutdown(wait=False)
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.unveil(str(STATIC_ROOT).encode(), b"r")
    libc.unveil(str(ASSETS_DIR).encode(), b"r")
    libc.unveil(b"/var/db/mails/mails.db", b"r")
    libc.unveil(b"/etc/ssl/cert.pem", b"r")
    libc.unveil(None, None)
    r = libc.pledge(b"stdio inet dns rpath flock", None)
    if r != 0:
        raise OSError(ctypes.get_errno(), "pledge failed")


async def checker_loop(path, checker, interval):
    while True:
        t0 = time.monotonic()
        try:
            log.info("checking %s ...", path)
            data = await asyncio.get_event_loop().run_in_executor(None, checker.check)
            now = time.time()
            state[path].update(data=data, last_updated=now, next_update=now + interval)
            n = len(data.get("messages", data.get("binaries", [])))
            log.info("done %s in %.1fs (%d items)", path, time.monotonic() - t0, n)
        except Exception as e:
            log.error("check failed %s: %s", path, e)
        await asyncio.sleep(interval)


def make_api_handler(path):
    async def handler(request):
        s = state[path]
        if s["data"] is None:
            return web.json_response({"status": "checking"}, status=503)
        return web.json_response({"last_updated": s["last_updated"],
                                  "next_update": s["next_update"], "data": s["data"]})
    return handler


# === MAILS ===

def make_mails_page(title, api_path):
    async def handler(request):
        html = (ASSETS_DIR / "index.html").read_text().replace("__API_PATH__", api_path)
        return web.Response(text=html, content_type="text/html")
    return handler


def make_mails_assets(api_path):
    async def handler(request):
        rel = request.match_info.get("path", "index.html")
        p = ASSETS_DIR / rel
        if not p.exists() or not p.is_file():
            raise web.HTTPNotFound()
        mime, _ = mimetypes.guess_type(str(p))
        if rel == "app.js":
            text = p.read_text().replace("__API_PATH__", api_path)
            return web.Response(text=text, content_type="application/javascript")
        return web.FileResponse(p, headers={"Content-Type": mime or "application/octet-stream"})
    return handler


async def mails_msg(request):
    data, err = await asyncio.get_event_loop().run_in_executor(
        None, mail_checker.fetch_body, None, request.match_info["id"])
    return web.json_response(data if not err else {"error": err}, status=200 if not err else 404 if err == "not found" else 502)


async def mails_thread(request):
    data, err = await asyncio.get_event_loop().run_in_executor(
        None, mail_checker.fetch_thread, request.match_info["id"])
    return web.json_response(data if not err else {"error": err}, status=200 if not err else 404 if err == "thread not found" else 502)


# === MIRRORS ===

def make_mirrors_page(title, api_path):
    async def handler(request):
        return web.Response(text=_MIRRORS_HTML, content_type="text/html")
    return handler


_MIRRORS_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenBSD Mirror Status</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#1a1a1a;--bg2:#222222;--bg3:#2a2a2a;
  --border:#333333;--border2:#444444;
  --text:#e0e0e0;--text2:#999999;--text3:#666666;
  --accent:#c8a96e;
  --ok:#4caf6e;--ok2:#2d6b42;
  --dead:#c0392b;--dead2:#5a1a14;
}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;line-height:1.5;min-height:100vh}
a{color:var(--accent);text-decoration:none}
.wrap{max-width:1400px;width:95%;margin:0 auto;padding:32px 0 80px}
header{display:flex;align-items:baseline;gap:24px;margin-bottom:28px;padding-bottom:16px;border-bottom:1px solid var(--border)}
header h1{font-size:16px;font-weight:600;color:var(--text);letter-spacing:.5px;text-transform:uppercase}
h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--text2);margin-bottom:16px}
.section{margin-bottom:40px}
.subtitle{font-size:12px;color:var(--text3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px}
.cmd-block{margin-bottom:12px}
.cmd-line{font-size:12px;color:var(--text2);padding:8px 14px;background:var(--bg2);border:1px solid var(--border);border-left:2px solid var(--accent);margin-bottom:4px;word-break:break-all;font-family:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace}
.card{border:1px solid var(--border);background:var(--bg2)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;color:var(--text3);letter-spacing:2px;text-transform:uppercase;padding:8px 12px;border-bottom:1px solid var(--border)}
td{padding:7px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr.ok:hover td{background:var(--bg3)}
tr.dead td{color:var(--text3)}
tr.dead:hover td{background:var(--bg3)}
.status-dot{font-size:9px}
.dot-ok{color:var(--ok)}
.dot-dead{color:var(--dead)}
.proto-badge{display:inline-block;font-size:10px;padding:1px 5px;border:1px solid var(--border2);color:var(--text3);margin-right:2px;text-transform:uppercase;letter-spacing:.5px}
tr.ok .proto-badge{border-color:var(--ok2);color:var(--ok)}
.ms{font-size:12px;color:var(--text2);font-variant-numeric:tabular-nums}
.spinner{color:var(--text3);font-size:13px;margin:60px 0;text-align:center;letter-spacing:1px;text-transform:uppercase}
.status-bar{position:fixed;bottom:0;left:0;right:0;padding:6px 24px;background:var(--bg2);border-top:1px solid var(--border);display:flex;justify-content:space-between;font-size:11px;color:var(--text3)}
.status-bar span{color:var(--text2)}
</style></head><body>
<div class="wrap">
<header><h1>OpenBSD Mirror Status</h1></header>
<div id="content"><p class="spinner">fetching data...</p></div>
</div>
<div class="status-bar"><span>OpenBSD · aiohttp</span><span id="ts">—</span></div>
<script>
const API='/mirrors/api';
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function badge(p){return '<span class="proto-badge">'+esc(p)+'</span>'}
async function go(){
  try{
    const r=await fetch(API);
    if(r.status===503){document.getElementById('content').innerHTML='<p class="spinner">checking servers...</p>';setTimeout(go,3000);return}
    const j=await r.json();
    render(j.data);
    const u=new Date(j.last_updated*1000).toISOString().replace('T',' ').slice(0,16)+' UTC';
    setInterval(()=>{
      const s=Math.max(0,Math.round((j.next_update*1000-Date.now())/1000));
      const m=Math.floor(s/60),ss=s%60;
      document.getElementById('ts').textContent='Updated '+u+' · refresh in '+(s>0?m+':'+String(ss).padStart(2,'0'):'updating...')
    },1000)
  }catch(e){document.getElementById('content').innerHTML='<p class="spinner">error: '+e.message+'</p>';setTimeout(go,10000)}
}
function render(d){
  let h='';
  h+='<div class="section"><h2>Binaries</h2>';
  h+='<p class="subtitle">pkg_add · iso · firmware</p>';
  if(d.binaries[0])h+='<div class="cmd-block"><div class="cmd-line">PKG_PATH='+esc(d.binaries[0].best_url)+' pkg_add &lt;package&gt;</div></div>';
  h+='<div class="card"><table><thead><tr><th></th><th>Host</th><th>Country</th><th>Proto</th><th>ms</th></tr></thead><tbody>';
  d.binaries.forEach(m=>{h+='<tr class="ok"><td><span class="status-dot dot-ok">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td>'+m.protos.map(badge).join('')+'</td><td class="ms">'+m.ms+'</td></tr>'});
  d.binary_dead.forEach(m=>{h+='<tr class="dead"><td><span class="status-dot dot-dead">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td></td><td></td></tr>'});
  h+='</tbody></table></div></div>';
  h+='<div class="section"><h2>CVS (anoncvs)</h2>';
  h+='<p class="subtitle">src · ports · xenocara</p>';
  if(d.cvs_cmds)d.cvs_cmds.forEach(c=>{h+='<div class="cmd-block"><div class="cmd-line">'+esc(c)+'</div></div>'});
  h+='<div class="card"><table><thead><tr><th></th><th>Host</th><th>Country</th><th>Proto</th><th>ms</th></tr></thead><tbody>';
  d.cvs.forEach(m=>{const p=m.port!==22&&m.port!==2401?':'+m.port:'';h+='<tr class="ok"><td><span class="status-dot dot-ok">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td>'+badge(m.proto+p)+'</td><td class="ms">'+m.ms+'</td></tr>'});
  d.cvs_dead.forEach(m=>{h+='<tr class="dead"><td><span class="status-dot dot-dead">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td></td><td></td></tr>'});
  h+='</tbody></table></div></div>';
  document.getElementById('content').innerHTML=h;
}
go();
</script></body></html>"""


# === STATIC ===

async def static_handler(request):
    rel = request.path.lstrip("/") or "index.html"
    path = STATIC_ROOT / rel
    if path.is_dir(): path = path / "index.html"
    if not path.exists() or not path.is_file(): raise web.HTTPNotFound()
    mime, _ = mimetypes.guess_type(str(path))
    return web.FileResponse(path, headers={"Content-Type": mime or "application/octet-stream"})


# === APP ===

async def on_startup(app):
    app["tasks"] = []
    for path, checker, interval, _ in REGISTRY:
        app["tasks"].append(asyncio.create_task(checker_loop(path, checker, interval)))
    harden()
    log.info("started %s:%d", HOST, PORT)

async def on_cleanup(app):
    for t in app["tasks"]: t.cancel()


def make_app():
    app = web.Application()

    # Mirrors
    app.router.add_get("/mirrors",    make_mirrors_page("OpenBSD Mirror Status", "/mirrors/api"))
    app.router.add_get("/mirrors/",  make_mirrors_page("OpenBSD Mirror Status", "/mirrors/api"))
    app.router.add_get("/mirrors/api", make_api_handler("/mirrors"))
    # Backward compat
    async def redir(r): raise web.HTTPMovedPermanently(location="/mirrors")
    app.router.add_get("/servers", redir)
    app.router.add_get("/servers/", redir)

    # Mails
    app.router.add_get("/mails",             make_mails_page("OpenBSD Mailing Lists", "/mails/api"))
    app.router.add_get("/mails/",           make_mails_page("OpenBSD Mailing Lists", "/mails/api"))
    app.router.add_get("/mails/api",        make_api_handler("/mails"))
    app.router.add_get("/mails/assets/{path:.*}", make_mails_assets("/mails/api"))
    app.router.add_get("/mails/msg/{id}",         mails_msg)
    app.router.add_get("/mails/thread/{id}",      mails_thread)

    # Static fallback
    app.router.add_get("/{tail:.*}", static_handler)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host=HOST, port=PORT, access_log=log)
