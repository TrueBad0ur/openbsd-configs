"""mail-svc: serves OpenBSD mailing list reader at /mails (dynamic)
and static files from assets/ and STATIC_ROOT.
"""

import asyncio
import mimetypes
import os
import sys
import time
import logging
from pathlib import Path
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mail as mail_checker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HOST        = "0.0.0.0"
PORT        = 8081
INTERVAL    = 600
STATIC_ROOT = Path("/var/www/htdocs")
ASSETS_DIR  = Path(os.path.dirname(os.path.abspath(__file__))) / "assets"

REGISTRY = [
    ("/mails", mail_checker, "OpenBSD Mailing Lists"),
]

state = {path: {"data": None, "last_updated": 0.0, "next_update": 0.0}
         for path, _, _ in REGISTRY}


# --- Background checker ---

async def checker_loop(path, checker, interval):
    while True:
        t0 = time.monotonic()
        try:
            log.info("fetching %s ...", path)
            data = await asyncio.get_event_loop().run_in_executor(None, checker.check)
            now = time.time()
            state[path].update(data=data, last_updated=now, next_update=now + interval)
            log.info("done %s in %.1fs (%d messages)", path, time.monotonic() - t0,
                     len(data.get("messages", [])))
        except Exception as e:
            log.error("check failed for %s: %s", path, e)
        await asyncio.sleep(interval)


# --- API handler ---

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


# --- Message body handler ---

async def msg_handler(request):
    list_name = request.match_info["list"]
    message_id = request.match_info["id"]
    data, err = await asyncio.get_event_loop().run_in_executor(
        None, mail_checker.fetch_body, list_name, message_id)
    if err:
        return web.json_response({"error": err}, status=502)
    return web.json_response(data)


# --- Thread handler ---

async def thread_handler(request):
    thread_id = request.match_info["id"]
    data, err = await asyncio.get_event_loop().run_in_executor(
        None, mail_checker.fetch_thread, thread_id)
    if err:
        return web.json_response({"error": err}, status=502)
    return web.json_response(data)


# --- Page handler: reads index.html, injects API path ---

def make_page_handler(title, api_path):
    index_html = (ASSETS_DIR / "index.html").read_text()
    index_html = index_html.replace("__API_PATH__", api_path)

    async def handler(request):
        return web.Response(text=index_html, content_type="text/html")
    return handler


# --- Static assets handler (injects API path into app.js) ---

JS_TEMPLATE = (ASSETS_DIR / "app.js").read_text()

def make_assets_handler(api_path):
    js_content = JS_TEMPLATE.replace("__API_PATH__", api_path)

    async def handler(request):
        rel = request.match_info.get("path", "index.html")
        path = ASSETS_DIR / rel
        if not path.exists() or not path.is_file():
            raise web.HTTPNotFound()
        mime, _ = mimetypes.guess_type(str(path))
        if rel == "app.js":
            return web.Response(text=js_content, content_type="application/javascript")
        return web.FileResponse(path, headers={"Content-Type": mime or "application/octet-stream"})
    return handler


# --- Static file handler (for STATIC_ROOT) ---

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
    log.info("started")


async def on_cleanup(app):
    for t in app["tasks"]:
        t.cancel()


def make_app():
    app = web.Application()
    for path, _, title in REGISTRY:
        api_path = path + "/api"
        app.router.add_get(path,          make_page_handler(title, api_path))
        app.router.add_get(path + "/",    make_page_handler(title, api_path))
        app.router.add_get(api_path,      make_api_handler(path))
        app.router.add_get(path + "/assets/{path:.*}", make_assets_handler(api_path))
    app.router.add_get("/mails/msg/{list}/{id}", msg_handler)
    app.router.add_get("/mails/thread/{id}", thread_handler)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    app = make_app()
    web.run_app(app, host=HOST, port=PORT, access_log=log)
