#!/usr/bin/env python3
import email
import email.header
import email.utils
import re
import sqlite3
import sys
from datetime import timezone

DB_PATH = "/var/db/mails/mails.db"

LIST_MAP = {
    "<tech.openbsd.org>":                 "openbsd-tech",
    "<misc.openbsd.org>":                 "openbsd-misc",
    "<ports.openbsd.org>":                "openbsd-ports",
    "<cvs.openbsd.org>":                  "openbsd-cvs",
    "<announce.openbsd.org>":             "openbsd-announce",
    "<www.openbsd.org>":                  "openbsd-www",
    "<bugs.openbsd.org>":                 "openbsd-bugs",
    "<pf.openbsd.org>":                   "openbsd-pf",
    "<security-announce.openbsd.org>":    "openbsd-security-announce",
    "<newbies.openbsd.org>":              "openbsd-newbies",
    "<mirrors.openbsd.org>":              "openbsd-mirrors",
    "<advocacy.openbsd.org>":             "openbsd-advocacy",
    "<mobile.openbsd.org>":               "openbsd-mobile",
    "<arm.openbsd.org>":                  "openbsd-arm",
    "<alpha.openbsd.org>":                "openbsd-alpha",
    "<sparc.openbsd.org>":                "openbsd-sparc",
    "<ppc.openbsd.org>":                  "openbsd-ppc",
    "<hppa.openbsd.org>":                 "openbsd-hppa",
    "<smp.openbsd.org>":                  "openbsd-smp",
    "<x11.openbsd.org>":                  "openbsd-x11",
    "<ipv6.openbsd.org>":                 "openbsd-ipv6",
    "<mac68k.openbsd.org>":               "openbsd-mac68k",
    "<m88k.openbsd.org>":                 "openbsd-m88k",
    "<vax.openbsd.org>":                  "openbsd-vax",
    "<sgi.openbsd.org>":                  "openbsd-sgi",
    "<elf.openbsd.org>":                  "openbsd-elf",
    "<libressl.openbsd.org>":             "openbsd-libressl",
    "<security.openbsd.org>":             "openbsd-security",
    "<libressl-security.openbsd.org>":    "openbsd-libressl-security",
    "<opensmtpd-security.openbsd.org>":   "openbsd-opensmtpd-security",
    "<mirrors-announce.openbsd.org>":     "openbsd-mirrors-announce",
    "<mirrors-discuss.openbsd.org>":      "openbsd-mirrors-discuss",
    "<source-changes.openbsd.org>":       "openbsd-source-changes",
    "tech@openbsd.org":                   "openbsd-tech",
    "misc@openbsd.org":                   "openbsd-misc",
    "ports@openbsd.org":                  "openbsd-ports",
    "cvs@openbsd.org":                    "openbsd-cvs",
    "announce@openbsd.org":               "openbsd-announce",
    "www@openbsd.org":                    "openbsd-www",
    "bugs@openbsd.org":                   "openbsd-bugs",
    "pf@openbsd.org":                     "openbsd-pf",
    "security-announce@openbsd.org":      "openbsd-security-announce",
    "newbies@openbsd.org":                "openbsd-newbies",
    "mirrors@openbsd.org":                "openbsd-mirrors",
    "advocacy@openbsd.org":               "openbsd-advocacy",
    "mobile@openbsd.org":                 "openbsd-mobile",
    "arm@openbsd.org":                    "openbsd-arm",
    "alpha@openbsd.org":                  "openbsd-alpha",
    "sparc@openbsd.org":                  "openbsd-sparc",
    "ppc@openbsd.org":                    "openbsd-ppc",
    "hppa@openbsd.org":                   "openbsd-hppa",
    "smp@openbsd.org":                    "openbsd-smp",
    "x11@openbsd.org":                    "openbsd-x11",
    "ipv6@openbsd.org":                   "openbsd-ipv6",
    "mac68k@openbsd.org":                 "openbsd-mac68k",
    "m88k@openbsd.org":                   "openbsd-m88k",
    "vax@openbsd.org":                    "openbsd-vax",
    "sgi@openbsd.org":                    "openbsd-sgi",
    "elf@openbsd.org":                    "openbsd-elf",
    "libressl@openbsd.org":               "openbsd-libressl",
    "security@openbsd.org":               "openbsd-security",
    "libressl-security@openbsd.org":      "openbsd-libressl-security",
    "opensmtpd-security@openbsd.org":     "openbsd-opensmtpd-security",
    "mirrors-announce@openbsd.org":       "openbsd-mirrors-announce",
    "mirrors-discuss@openbsd.org":        "openbsd-mirrors-discuss",
    "source-changes@openbsd.org":         "openbsd-source-changes",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    list        TEXT NOT NULL,
    message_id  TEXT NOT NULL UNIQUE,
    in_reply_to TEXT,
    refs        TEXT,
    subject     TEXT,
    from_addr   TEXT,
    date        TEXT,
    date_ts     INTEGER,
    body        TEXT,
    received_at INTEGER DEFAULT (strftime('%s', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_list    ON messages(list);
CREATE INDEX IF NOT EXISTS idx_date    ON messages(date_ts DESC);
CREATE INDEX IF NOT EXISTS idx_reply   ON messages(in_reply_to);
CREATE INDEX IF NOT EXISTS idx_msgid   ON messages(message_id);
"""


def decode_header(value):
    if not value:
        return ""
    parts = email.header.decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result).strip()


def identify_list(msg):
    """Return canonical list name, or raw List-Id value, or 'unknown'. Never returns None."""
    headers = [
        msg.get("List-Id", ""),
        msg.get("Delivered-To", ""),
        msg.get("To", ""),
        msg.get("Cc", ""),
        msg.get("X-Mailing-List", ""),
        msg.get("X-BeenThere", ""),
    ]
    combined = " ".join(headers).lower()
    for pattern, canonical in LIST_MAP.items():
        if pattern.lower() in combined:
            return canonical
    # Not in LIST_MAP — store with raw List-Id so data is never lost
    raw = msg.get("List-Id", "").strip()
    return raw if raw else "unknown"


def extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                try:
                    return part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            return msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            return str(msg.get_payload())


def parse_date(date_str):
    if not date_str:
        return "", 0
    try:
        t = email.utils.parsedate_to_datetime(date_str)
        return t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), int(t.timestamp())
    except Exception:
        return date_str.strip(), 0


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def insert(conn, row):
    try:
        conn.execute("""
            INSERT OR IGNORE INTO messages
                (list, message_id, in_reply_to, refs, subject, from_addr, date, date_ts, body)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row)
        conn.commit()
    except sqlite3.Error as e:
        sys.stderr.write(f"processor: db error: {e}\n")


def harden():
    import platform, ctypes, ctypes.util, sys
    if platform.system() != "OpenBSD":
        return
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.unveil((sys.prefix + "/lib").encode(),  b"r")   # Python stdlib (.py modules loaded lazily)
    libc.unveil(DB_PATH.encode(),                b"rwc")
    libc.unveil(b"/var/db/mails/majordomo.log",  b"rwc")
    libc.unveil(b"/var/db/mails",                b"rwc")
    libc.unveil(None, None)
    libc.pledge(b"stdio rpath wpath cpath flock chown", None)


def main():
    harden()
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    raw = sys.stdin.buffer.read()
    msg = email.message_from_bytes(raw)

    # Majordomo confirmations go to a log file, not the messages DB
    from_hdr = msg.get("From", "") + msg.get("Return-Path", "")
    if "majordomo" in from_hdr.lower():
        try:
            with open("/var/db/mails/majordomo.log", "a") as f:
                f.write(f"\n{'='*60}\n")
                for h in ("From", "Return-Path", "Subject", "Date"):
                    f.write(f"{h}: {msg.get(h, '')}\n")
                f.write("\n" + extract_body(msg) + "\n")
        except Exception:
            pass
        conn.close()
        sys.exit(0)

    # message_id is required for deduplication — skip only if truly absent
    message_id = decode_header(msg.get("Message-Id", "")).strip("<>")
    if not message_id:
        conn.close()
        sys.exit(0)

    lst = identify_list(msg)
    if lst not in LIST_MAP.values():
        sys.stderr.write(
            f"processor: unknown list {lst!r}: "
            f"from={msg.get('From', '')} subject={msg.get('Subject', '')}\n"
        )

    raw_irt = decode_header(msg.get("In-Reply-To", ""))
    irt_m = re.search(r'<([^>]+)>', raw_irt)
    in_reply_to = (irt_m.group(1) if irt_m else raw_irt.strip()) or None

    refs_raw = decode_header(msg.get("References", ""))
    refs = " ".join(re.findall(r'<([^>]+)>', refs_raw)) or None

    subject  = decode_header(msg.get("Subject", "(no subject)"))
    from_addr = decode_header(msg.get("From", ""))
    date_str, date_ts = parse_date(msg.get("Date", ""))
    body = extract_body(msg)

    insert(conn, (lst, message_id, in_reply_to, refs, subject, from_addr, date_str, date_ts, body))
    conn.close()


if __name__ == "__main__":
    main()
