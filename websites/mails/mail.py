"""OpenBSD mailing lists reader — reads from local SQLite DB."""

import re
import sqlite3
from collections import Counter, defaultdict

DB_PATH = "/var/db/mails/mails.db"

OPENBSD_LISTS = [
    "openbsd-tech", "openbsd-misc", "openbsd-ports", "openbsd-announce",
    "openbsd-bugs", "openbsd-www", "openbsd-pf", "openbsd-security-announce",
    "openbsd-newbies", "openbsd-mirrors", "openbsd-advocacy", "openbsd-mobile",
    "openbsd-arm", "openbsd-alpha", "openbsd-sparc", "openbsd-ppc",
    "openbsd-hppa", "openbsd-smp", "openbsd-x11", "openbsd-ipv6",
    "openbsd-mac68k", "openbsd-m88k", "openbsd-vax", "openbsd-sgi",
    "openbsd-elf", "openbsd-cvs",
    "openbsd-libressl", "openbsd-security", "openbsd-libressl-security",
    "openbsd-opensmtpd-security", "openbsd-mirrors-announce",
    "openbsd-mirrors-discuss", "openbsd-source-changes",
]


def _conn():
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _msg_meta(row):
    return {
        "id":          row["id"],
        "list":        row["list"],
        "message_id":  row["message_id"],
        "in_reply_to": row["in_reply_to"],
        "subject":     row["subject"] or "(no subject)",
        "author":      row["from_addr"] or "",
        "date":        row["date"] or "",
        "date_ts":     row["date_ts"] or 0,
    }


def _build_threads(messages):
    by_msgid = {m["message_id"]: m for m in messages}

    root_cache = {}

    def root_of(mid):
        if mid in root_cache:
            return root_cache[mid]
        seen, cur = set(), mid
        while True:
            if cur in seen:
                break
            seen.add(cur)
            m = by_msgid.get(cur)
            if not m:
                break
            parent = m.get("in_reply_to")
            if not parent or parent not in by_msgid:
                break
            cur = parent
        for k in seen:
            root_cache[k] = cur
        return cur

    by_root = defaultdict(list)
    for m in messages:
        root_mid = root_of(m["message_id"])
        root = by_msgid.get(root_mid)
        by_root[root["id"] if root else m["id"]].append(m)

    result = []
    for root_id, msgs in by_root.items():
        msgs.sort(key=lambda m: m["date_ts"] or 0)
        clean_subj = re.sub(r'^(?:Re|Fw|Fwd|Aw):\s*', '', msgs[0]["subject"], flags=re.IGNORECASE).strip()
        result.append({
            "thread_id": root_id,
            "subject":   clean_subj or msgs[0]["subject"],
            "count":     len(msgs),
            "last_date": msgs[-1]["date"],
            "last_ts":   msgs[-1]["date_ts"] or 0,
            "authors":   list(dict.fromkeys(m["author"] for m in msgs if m["author"])),
            "lists":     list(dict.fromkeys(m["list"] for m in msgs)),
        })

    result.sort(key=lambda t: t["last_ts"], reverse=True)
    return result


def check():
    """Entry point for checker_loop — returns metadata from DB (no bodies)."""
    try:
        conn = _conn()
        rows = conn.execute("""
            SELECT id, list, message_id, in_reply_to, subject, from_addr, date, date_ts
            FROM messages
            ORDER BY date_ts DESC
            LIMIT 2000
        """).fetchall()
        conn.close()
    except Exception:
        return {
            "messages": [], "threads": [], "stats": {},
            "lists": OPENBSD_LISTS, "list_counts": {},
        }

    messages = [_msg_meta(r) for r in rows]
    threads = _build_threads(messages)

    author_cnt = Counter(m["author"] for m in messages if m["author"])
    list_cnt   = Counter(m["list"]   for m in messages)

    stats = {
        "total":          len(messages),
        "top_authors":    [{"name": n, "count": c} for n, c in author_cnt.most_common(20)],
        "list_breakdown": [{"list": l, "count": c} for l, c in list_cnt.most_common()],
    }

    return {
        "messages":   messages,
        "threads":    threads,
        "stats":      stats,
        "lists":      OPENBSD_LISTS,
        "list_counts": dict(list_cnt),
    }


def fetch_body(_list, msg_id):
    """Fetch single message with body by DB integer id."""
    try:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (int(msg_id),)
        ).fetchone()
        conn.close()
    except Exception as e:
        return None, str(e)

    if not row:
        return None, "not found"

    return {
        "id":          row["id"],
        "list":        row["list"],
        "message_id":  row["message_id"],
        "in_reply_to": row["in_reply_to"],
        "subject":     row["subject"] or "(no subject)",
        "author":      row["from_addr"] or "",
        "date":        row["date"] or "",
        "body":        row["body"] or "",
    }, None


def fetch_thread(thread_id):
    """Fetch all messages in a thread by root message DB id (BFS via in_reply_to)."""
    try:
        conn = _conn()
        root = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (int(thread_id),)
        ).fetchone()
        if not root:
            conn.close()
            return None, "thread not found"

        collected = {root["message_id"]: dict(root)}
        queue = [root["message_id"]]
        while queue:
            parent_mid = queue.pop(0)
            children = conn.execute(
                "SELECT * FROM messages WHERE in_reply_to = ?", (parent_mid,)
            ).fetchall()
            for child in children:
                if child["message_id"] not in collected:
                    collected[child["message_id"]] = dict(child)
                    queue.append(child["message_id"])
        conn.close()
    except Exception as e:
        return None, str(e)

    msgs = sorted(collected.values(), key=lambda m: m.get("date_ts") or 0)
    subject = re.sub(r'^(?:Re|Fw|Fwd|Aw):\s*', '', msgs[0].get("subject") or "", flags=re.IGNORECASE).strip()

    return {
        "thread_id": int(thread_id),
        "subject":   subject or msgs[0].get("subject", ""),
        "count":     len(msgs),
        "messages": [{
            "id":          m["id"],
            "list":        m["list"],
            "subject":     m.get("subject") or "(no subject)",
            "author":      m.get("from_addr") or "",
            "date":        m.get("date") or "",
            "body":        m.get("body") or "",
            "in_reply_to": m.get("in_reply_to"),
        } for m in msgs],
    }, None
