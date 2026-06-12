#!/usr/bin/env python3
"""Unified OpenBSD websites server.

Serves /mirrors (mirror status) and /mails (mailing lists) on port 8080.
Behind relayd:443 → Anubis:8923 → this service.
"""

import asyncio
import concurrent.futures
import concurrent.futures.thread
import concurrent.futures.process
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
    ("/mails",   mail_checker,    600, "OpenBSD Mailing Lists"),
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
    libc.unveil(b"/etc/ssl/cert.pem", b"r")
    libc.unveil(None, None)
    r = libc.pledge(b"stdio inet dns rpath", None)
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

MAILS_INDEX = None
MAILS_JS = None

def _load_mails():
    global MAILS_INDEX, MAILS_JS
    if MAILS_INDEX is None:
        MAILS_INDEX = (ASSETS_DIR / "index.html").read_text()
        MAILS_JS = (ASSETS_DIR / "app.js").read_text()


def make_mails_page(title, api_path):
    _load_mails()
    html = MAILS_INDEX.replace("__API_PATH__", api_path)
    async def handler(request):
        return web.Response(text=html, content_type="text/html")
    return handler


def make_mails_assets(api_path):
    _load_mails()
    js = MAILS_JS.replace("__API_PATH__", api_path)
    async def handler(request):
        rel = request.match_info.get("path", "index.html")
        if rel == "app.js":
            return web.Response(text=js, content_type="application/javascript")
        p = ASSETS_DIR / rel
        if not p.exists() or not p.is_file():
            raise web.HTTPNotFound()
        mime, _ = mimetypes.guess_type(str(p))
        return web.FileResponse(p, headers={"Content-Type": mime or "application/octet-stream"})
    return handler


async def mails_msg(request):
    data, err = await asyncio.get_event_loop().run_in_executor(
        None, mail_checker.fetch_body, request.match_info["list"], request.match_info["id"])
    return web.json_response(data if not err else {"error": err}, status=200 if not err else 502)


async def mails_thread(request):
    data, err = await asyncio.get_event_loop().run_in_executor(
        None, mail_checker.fetch_thread, request.match_info["id"])
    return web.json_response(data if not err else {"error": err}, status=200 if not err else 502)


# === MIRRORS ===

MIRRORS_JS = None

def _load_mirrors():
    global MIRRORS_JS
    if MIRRORS_JS is None:
        # Inline the mirrors page (same as original mirrors-svc)
        pass


def make_mirrors_page(title, api_path):
    async def handler(request):
        return web.Response(text=_MIRRORS_HTML, content_type="text/html")
    return handler


_MIRRORS_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenBSD Mirror Status</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#00ff41;font-family:'Share Tech Mono',monospace;min-height:100vh}
body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.08) 2px,rgba(0,0,0,.08) 4px);pointer-events:none;z-index:100}
.terminal{max-width:960px;margin:0 auto;padding:60px 24px 80px}
.term-header{display:flex;align-items:center;gap:8px;margin-bottom:40px;padding-bottom:16px;border-bottom:1px solid #1a1a1a}
.dot{width:12px;height:12px;border-radius:50%}
.dot-r{background:#ff5f57;box-shadow:0 0 6px #ff5f57}.dot-y{background:#ffbd2e;box-shadow:0 0 6px #ffbd2e}.dot-g{background:#28c840;box-shadow:0 0 6px #28c840}
.back{font-size:13px;color:#00aa2a;text-decoration:none;margin-left:auto}.back:hover{color:#00ff41}
h2{font-size:32px;color:#00ff41;letter-spacing:2px;margin-bottom:6px}
.cmd-block{margin-bottom:16px}
.cmd-line{font-size:12px;color:#00aa2a;padding:6px 12px;background:#0d0d0d;border-left:2px solid #00aa2a;margin-bottom:4px;word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;color:#444;letter-spacing:3px;text-transform:uppercase;padding:8px 10px 8px 0;border-bottom:1px solid #1c1c1c}
td{padding:6px 10px 6px 0;border-bottom:1px solid #111;vertical-align:middle}
.ok{color:#00ff41}.dead{color:#444}
.dot-ok{color:#00ff41;text-shadow:0 0 6px #00ff41;font-size:10px}
.dot-dead{color:#ff4444;text-shadow:0 0 4px #ff4444;font-size:10px}
.protos{color:#00aa2a;font-size:12px}.dead .protos{color:#333}
.ms{color:#007a1f;font-size:12px;white-space:nowrap}.dead .ms{color:#333}
.spinner{color:#555;font-size:13px;margin:40px 0}
.section{margin-bottom:48px}
.status-line{position:fixed;bottom:0;left:0;right:0;padding:6px 24px;background:#080808;border-top:1px solid #1a1a1a;display:flex;justify-content:space-between;font-size:11px;color:#333;z-index:50;letter-spacing:1px}
.status-line span{color:#00aa2a}.ts{color:#555}
</style></head><body>
<div class="terminal">
<div class="term-header"><div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div>
<span style="font-size:12px;color:#444;margin-left:8px;letter-spacing:2px">truebad0ur@openbsd ~ — ssh</span>
<a class="back" href="/">&larr; back</a></div>
<div id="content"><p class="spinner">fetching data...</p></div></div>
<div class="status-line"><span>OpenBSD 7.9 · aiohttp</span><span class="ts" id="ts">—</span></div>
<script>
const API='/mirrors/api';let _d=null;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
async function go(){try{const r=await fetch(API);if(r.status===503){document.getElementById('content').innerHTML='<p class="spinner">checking servers...</p>';setTimeout(go,3000);return}const j=await r.json();_d=j.data;render(j.data);const u=new Date(j.last_updated*1000).toISOString().replace('T',' ').slice(0,16)+' UTC';setInterval(()=>{const s=Math.max(0,Math.round((j.next_update*1000-Date.now())/1000));const m=Math.floor(s/60),ss=s%60;document.getElementById('ts').textContent='updated: '+u+' · refresh in '+(s>0?m+':'+String(ss).padStart(2,'0'):'updating...')},1000)}catch(e){document.getElementById('content').innerHTML='<p class="spinner">error: '+e.message+'</p>';setTimeout(go,10000)}}
function render(d){let h='<div class="section"><h2>BINARIES</h2><p style="font-size:11px;color:#444;margin-bottom:14px;letter-spacing:1px">pkg_add · iso · firmware</p>';h+='<div class="cmd-block"><div class="cmd-line">$ PKG_PATH='+(d.binaries[0]?esc(d.binaries[0].best_url):'')+' pkg_add &lt;package&gt;</div></div>';h+='<table><thead><tr><th></th><th>country</th><th>proto</th><th>host</th><th>ms</th></tr></thead><tbody>';d.binaries.forEach(m=>{h+='<tr class="ok"><td><span class="dot-ok">●</span></td><td>'+esc(m.country)+'</td><td class="protos">'+esc(m.protos.join(' '))+'</td><td>'+esc(m.host)+'</td><td class="ms">'+m.ms+'ms</td></tr>'});d.binary_dead.forEach(m=>{h+='<tr class="dead"><td><span class="dot-dead">●</span></td><td>'+esc(m.country)+'</td><td></td><td>'+esc(m.host)+'</td><td></td></tr>'});h+='</tbody></table></div>';h+='<div class="section"><h2>CVS (anoncvs)</h2><p style="font-size:11px;color:#444;margin-bottom:14px;letter-spacing:1px">src · ports · xenocara</p>';if(d.cvs_cmds){d.cvs_cmds.forEach(c=>{h+='<div class="cmd-block"><div class="cmd-line">$ '+esc(c)+'</div></div>'})}h+='<table><thead><tr><th></th><th>country</th><th>proto</th><th>host</th><th>ms</th></tr></thead><tbody>';d.cvs.forEach(m=>{const p=m.port!==22&&m.port!==2401?':'+m.port:'';h+='<tr class="ok"><td><span class="dot-ok">●</span></td><td>'+esc(m.country)+'</td><td class="protos">'+esc(m.proto+p)+'</td><td>'+esc(m.host)+'</td><td class="ms">'+m.ms+'ms</td></tr>'});d.cvs_dead.forEach(m=>{h+='<tr class="dead"><td><span class="dot-dead">●</span></td><td>'+esc(m.country)+'</td><td></td><td>'+esc(m.host)+'</td><td></td></tr>'});h+='</tbody></table></div>';document.getElementById('content').innerHTML=h}
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
    app.router.add_get("/mails/msg/{list}/{id}",  mails_msg)
    app.router.add_get("/mails/thread/{id}",      mails_thread)

    # Static fallback
    app.router.add_get("/{tail:.*}", static_handler)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host=HOST, port=PORT, access_log=log)
