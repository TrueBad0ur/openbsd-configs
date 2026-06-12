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
MIRRORS_ASSETS_DIR = SVC_DIR / "mirrors-assets"

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
    libc.unveil(str(MIRRORS_ASSETS_DIR).encode(), b"r")
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
        html = (MIRRORS_ASSETS_DIR / "index.html").read_text()
        return web.Response(text=html, content_type="text/html")
    return handler


def make_mirrors_assets():
    async def handler(request):
        rel = request.match_info.get("path", "index.html")
        p = MIRRORS_ASSETS_DIR / rel
        if not p.exists() or not p.is_file():
            raise web.HTTPNotFound()
        mime, _ = mimetypes.guess_type(str(p))
        return web.FileResponse(p, headers={"Content-Type": mime or "application/octet-stream"})
    return handler


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
    app.router.add_get("/mirrors",              make_mirrors_page("OpenBSD Mirror Status", "/mirrors/api"))
    app.router.add_get("/mirrors/",            make_mirrors_page("OpenBSD Mirror Status", "/mirrors/api"))
    app.router.add_get("/mirrors/api",         make_api_handler("/mirrors"))
    app.router.add_get("/mirrors/assets/{path:.*}", make_mirrors_assets())
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
