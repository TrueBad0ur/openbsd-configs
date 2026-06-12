"""marc.info scraper for OpenBSD mailing lists."""

import re
import time
import html
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

MARC_BASE = "https://marc.info"

OPENBSD_LISTS = [
    "openbsd-tech",
    "openbsd-cvs",
    "openbsd-ports",
    "openbsd-misc",
    "openbsd-announce",
    "openbsd-security-announce",
    "openbsd-www",
]

TIMEOUT = 15

# --- Regex patterns ---

MSG_LINK_RE = re.compile(
    r'<a\s+href="\?l=([^"&]+)(?:&amp;|&)m=(\d+)(?:&amp;|&)w=\d+">\s*(.*?)\s*</a>',
    re.DOTALL,
)

# Thread link: <a href="?t=THREAD_ID&r=1&w=2&n=N">N</a>
THREAD_RE = re.compile(
    r'<a\s+href="\?t=(\d+)(?:&amp;|&)r=1(?:&amp;|&)w=\d+(?:&amp;|&)n=\d+">\s*(\d+)\s*</a>'
)

DATE_RE = re.compile(r'\d+\.\s+(\d{4}-\d{2}-\d{2})')


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "openbsd-mail-reader/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def _decode(s):
    return html.unescape(s).strip()


# --- Index page parser ---

def fetch_month_index(list_name, year_month):
    """Fetch message listing from marc.info for a list+month.

    Extracts: message_id, thread_id, subject, author, date, replies.
    """
    url = f"{MARC_BASE}/?l={list_name}&r=1&b={year_month}&w=4"
    try:
        text = _fetch(url)
    except Exception as e:
        return [], str(e)

    messages = []
    for line in text.split("\n"):
        line = line.strip()
        if "&m=" not in line or list_name not in line:
            continue

        date_m = DATE_RE.search(line)
        if not date_m:
            continue

        link_m = MSG_LINK_RE.search(line)
        if not link_m:
            continue
        msg_list = _decode(link_m.group(1))
        msg_id = link_m.group(2)
        msg_subject = _decode(link_m.group(3))

        if msg_list != list_name:
            continue

        # Thread ID from ?t= link
        thread_m = THREAD_RE.search(line)
        thread_id = thread_m.group(1) if thread_m else msg_id
        thread_count = int(thread_m.group(2)) if thread_m else 1

        # Reply count (total in thread from marc.info, or 0 for single)
        replies = thread_count - 1 if thread_count > 1 else 0

        # Author: plain text after last </a>
        last_a_end = line.rfind("</a>")
        if last_a_end > 0:
            after = line[last_a_end+5:].strip()
            after_clean = re.sub(r'<[^>]+>', '', after).strip()
            after_clean = re.sub(r'\s{2,}.*', '', after_clean)
            msg_author = _decode(after_clean) if after_clean else "unknown"
        else:
            msg_author = "unknown"

        messages.append({
            "list": msg_list,
            "date": msg_date if (msg_date := date_m.group(1)) else "",
            "subject": msg_subject,
            "author": msg_author,
            "message_id": msg_id,
            "thread_id": thread_id,
            "thread_count": thread_count,
            "replies": replies,
            "url": f"{MARC_BASE}/?l={msg_list}&m={msg_id}",
        })

    return messages, None


# --- Single message body ---

def fetch_body(list_name, message_id):
    """Fetch message body from marc.info.

    Uses the HTML page (already decoded) instead of raw base64.
    """
    page_url = f"{MARC_BASE}/?l={list_name}&m={message_id}&w=2"
    headers = {}
    body = ""
    try:
        text = _fetch(page_url)

        # Extract headers
        for hdr in ("Subject", "From", "Date"):
            m = re.search(rf'{hdr}:\s*(.*?)(?:\n|$)', text)
            if m:
                val = _decode(re.sub(r'<[^>]+>', '', m.group(1)).strip())
                if hdr == "From":
                    val = val.replace(' () ', '@').replace(' ! ', '.')
                headers[hdr.lower()] = val

        # Extract decoded body from <pre> block
        pre_m = re.search(r'<pre>(.*?)</pre>', text, re.DOTALL)
        if pre_m:
            pre = pre_m.group(1)
            # Strip HTML tags
            pre = re.sub(r'<[^>]+>', '', pre)
            pre = _decode(pre)

            lines = pre.split('\n')
            body_lines = []
            in_body = False
            for line in lines:
                stripped = line.strip()
                # Skip navigation, headers, [Download, [Attachment
                if any(stripped.startswith(s) for s in
                       ('[Download', '[Attachment', '[prev in', '[next in',
                        'List:', 'Subject:', 'From:', 'Date:', 'Message-ID:',
                        'Configure', 'About', 'Sponsored')):
                    continue
                if stripped.startswith(('List:', 'Subject:', 'From:', 'Date:', 'Message-ID:')):
                    continue
                # Start collecting after we see actual content
                if not in_body and stripped:
                    in_body = True
                if in_body:
                    body_lines.append(line)

            # Remove trailing [prev/next] navigation
            while body_lines and body_lines[-1].strip().startswith('[prev'):
                body_lines.pop()
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()

            body = '\n'.join(body_lines)

    except Exception as e:
        body = f"[error fetching body: {e}]"

    return {
        "list": list_name,
        "message_id": message_id,
        "subject": headers.get("subject", ""),
        "author": headers.get("from", ""),
        "date": headers.get("date", ""),
        "body": body,
        "url": f"{MARC_BASE}/?l={list_name}&m={message_id}",
    }, None


# --- Thread fetch: all messages in a thread ---

def fetch_thread(thread_id):
    """Fetch all messages in a marc.info thread.

    Uses the thread view: ?t=THREAD_ID&r=1&w=2
    Then fetches raw body for each message.
    """
    url = f"{MARC_BASE}/?t={thread_id}&r=1&w=2"
    try:
        text = _fetch(url)
    except Exception as e:
        return None, str(e)

    # Extract all message IDs from the thread view
    msg_ids = []
    for line in text.split("\n"):
        line = line.strip()
        m = MSG_LINK_RE.search(line)
        if m and "&m=" in m.group(0):
            msg_list = _decode(m.group(1))
            msg_id = m.group(2)
            msg_ids.append((msg_list, msg_id))

    if not msg_ids:
        return None, "no messages found in thread"

    # Fetch body for each message (with rate limiting)
    messages = []
    for list_name, msg_id in msg_ids:
        data, err = fetch_body(list_name, msg_id)
        if not err:
            messages.append(data)
        time.sleep(0.2)

    # Sort by date (oldest first for conversation view)
    messages.sort(key=lambda m: m.get("date", ""))

    return {
        "thread_id": thread_id,
        "count": len(messages),
        "subject": messages[0]["subject"] if messages else "",
        "messages": messages,
    }, None


# --- Threading ---

def build_threads(messages):
    """Group messages into threads.

    Priority: thread_id (from marc.info ?t= links) > subject normalization.
    """
    by_thread = defaultdict(list)
    orphans = []

    for msg in messages:
        tid = msg.get("thread_id", msg["message_id"])
        # If thread_id == message_id, it might be a singleton or a root
        # We still group by thread_id since marc.info uses root msg id as thread id
        by_thread[tid].append(msg)

    result = []
    for tid, msgs in by_thread.items():
        # Sort oldest first (chronological)
        msgs.sort(key=lambda m: m.get("date", ""))

        # Root message is the one without Re: in subject, or the oldest
        root = msgs[0]
        for m in msgs:
            if not re.match(r'^(?:Re|Fw|Fwd|Aw):\s*', m["subject"], re.IGNORECASE):
                root = m
                break

        # Thread count from marc.info (max thread_count across messages)
        thread_count = max((m.get("thread_count", 1) for m in msgs), default=1)

        result.append({
            "subject": re.sub(r'^(?:Re|Fw|Fwd|Aw):\s*', '', root["subject"], flags=re.IGNORECASE).strip(),
            "thread_id": tid,
            "messages": msgs,
            "count": thread_count,  # total expected (may have messages from prev month)
            "actual_count": len(msgs),
            "last_date": msgs[-1]["date"] if msgs else "",
            "authors": list({m["author"] for m in msgs}),
        })

    result.sort(key=lambda t: t["last_date"], reverse=True)
    return result


# --- Statistics ---

def compute_stats(messages):
    author_counts = defaultdict(int)
    date_counts = defaultdict(int)
    list_counts = defaultdict(int)

    for msg in messages:
        author_counts[msg["author"]] += 1
        date_counts[msg["date"]] += 1
        list_counts[msg["list"]] += 1

    top_authors = sorted(author_counts.items(), key=lambda x: -x[1])[:20]
    daily_activity = sorted(date_counts.items())
    list_breakdown = sorted(list_counts.items(), key=lambda x: -x[1])

    return {
        "total": len(messages),
        "top_authors": [{"name": a, "count": c} for a, c in top_authors],
        "daily_activity": [{"date": d, "count": c} for d, c in daily_activity],
        "list_breakdown": [{"list": l, "count": c} for l, c in list_breakdown],
    }


# --- Public API ---

def fetch_current_month(list_name):
    ym = datetime.now(timezone.utc).strftime("%Y%m")
    return fetch_month_index(list_name, ym)


def fetch_all_lists():
    all_data = {}
    for lst in OPENBSD_LISTS:
        msgs, err = fetch_current_month(lst)
        all_data[lst] = msgs if not err else []
        time.sleep(0.3)
    return all_data


def check():
    """Main entry point for checker_loop."""
    all_data = fetch_all_lists()
    all_messages = []
    for msgs in all_data.values():
        all_messages.extend(msgs)

    threads = build_threads(all_messages)
    stats = compute_stats(all_messages)

    return {
        "messages": all_messages,
        "threads": threads,
        "stats": stats,
        "lists": list(all_data.keys()),
        "list_counts": {k: len(v) for k, v in all_data.items()},
    }
