#!/usr/bin/env python3
"""
Mail processor: reads raw email from stdin (called by smtpd MDA),
parses it and inserts into SQLite database.
"""

import email
import email.header
import email.utils
import re
import sqlite3
import sys
from datetime import timezone

DB_PATH = "/var/db/mails/mails.db"

# Maps substrings found in List-Id / headers → canonical stored name
LIST_MAP = {
    "openbsd-tech":  "openbsd-tech",
    "openbsd-misc":  "openbsd-misc",
    "openbsd-ports": "openbsd-ports",
    "openbsd-cvs":   "openbsd-cvs",
    "openbsd-announce":          "openbsd-announce",
    "openbsd-security-announce": "openbsd-security-announce",
    "openbsd-www":   "openbsd-www",
    # OpenBSD list server uses short names in List-Id
    "<tech.openbsd.org>":     "openbsd-tech",
    "<misc.openbsd.org>":     "openbsd-misc",
    "<ports.openbsd.org>":    "openbsd-ports",
    "<cvs.openbsd.org>":      "openbsd-cvs",
    "<announce.openbsd.org>": "openbsd-announce",
    "<www.openbsd.org>":      "openbsd-www",
    "<bugs.openbsd.org>":     "openbsd-bugs",
    "<pf.openbsd.org>":       "openbsd-pf",
    "<security-announce.openbsd.org>": "openbsd-security-announce",
    "<newbies.openbsd.org>":  "openbsd-newbies",
    "<mirrors.openbsd.org>":  "openbsd-mirrors",
    "<advocacy.openbsd.org>": "openbsd-advocacy",
    "<mobile.openbsd.org>":   "openbsd-mobile",
    "<arm.openbsd.org>":      "openbsd-arm",
    "<alpha.openbsd.org>":    "openbsd-alpha",
    "<sparc.openbsd.org>":    "openbsd-sparc",
    "<ppc.openbsd.org>":      "openbsd-ppc",
    "<hppa.openbsd.org>":     "openbsd-hppa",
    "<smp.openbsd.org>":      "openbsd-smp",
    "<x11.openbsd.org>":      "openbsd-x11",
    "<ipv6.openbsd.org>":     "openbsd-ipv6",
    "<mac68k.openbsd.org>":   "openbsd-mac68k",
    "<m88k.openbsd.org>":     "openbsd-m88k",
    "<vax.openbsd.org>":      "openbsd-vax",
    "<sgi.openbsd.org>":      "openbsd-sgi",
    "<elf.openbsd.org>":      "openbsd-elf",
    "tech@openbsd.org":     "openbsd-tech",
    "misc@openbsd.org":     "openbsd-misc",
    "ports@openbsd.org":    "openbsd-ports",
    "cvs@openbsd.org":      "openbsd-cvs",
    "announce@openbsd.org": "openbsd-announce",
    "www@openbsd.org":      "openbsd-www",
    "bugs@openbsd.org":     "openbsd-bugs",
    "pf@openbsd.org":       "openbsd-pf",
    "security-announce@openbsd.org": "openbsd-security-announce",
    "newbies@openbsd.org":  "openbsd-newbies",
    "mirrors@openbsd.org":  "openbsd-mirrors",
    "advocacy@openbsd.org": "openbsd-advocacy",
    "mobile@openbsd.org":   "openbsd-mobile",
    "arm@openbsd.org":      "openbsd-arm",
    "alpha@openbsd.org":    "openbsd-alpha",
    "sparc@openbsd.org":    "openbsd-sparc",
    "ppc@openbsd.org":      "openbsd-ppc",
    "hppa@openbsd.org":     "openbsd-hppa",
    "smp@openbsd.org":      "openbsd-smp",
    "x11@openbsd.org":      "openbsd-x11",
    "ipv6@openbsd.org":     "openbsd-ipv6",
    "mac68k@openbsd.org":   "openbsd-mac68k",
    "m88k@openbsd.org":     "openbsd-m88k",
    "vax@openbsd.org":      "openbsd-vax",
    "sgi@openbsd.org":      "openbsd-sgi",
    "elf@openbsd.org":      "openbsd-elf",
    "<libressl.openbsd.org>":          "openbsd-libressl",
    "<security.openbsd.org>":          "openbsd-security",
    "<libressl-security.openbsd.org>": "openbsd-libressl-security",
    "<opensmtpd-security.openbsd.org>":"openbsd-opensmtpd-security",
    "<mirrors-announce.openbsd.org>":  "openbsd-mirrors-announce",
    "<mirrors-discuss.openbsd.org>":   "openbsd-mirrors-discuss",
    "<source-changes.openbsd.org>":    "openbsd-source-changes",
    "libressl@openbsd.org":            "openbsd-libressl",
    "security@openbsd.org":            "openbsd-security",
    "libressl-security@openbsd.org":   "openbsd-libressl-security",
    "opensmtpd-security@openbsd.org":  "openbsd-opensmtpd-security",
    "mirrors-announce@openbsd.org":    "openbsd-mirrors-announce",
    "mirrors-discuss@openbsd.org":     "openbsd-mirrors-discuss",
    "source-changes@openbsd.org":      "openbsd-source-changes",
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


def extract_list(msg):
    """Detect which OpenBSD list this message is from."""
    headers_to_check = [
        msg.get("List-Id", ""),
        msg.get("Delivered-To", ""),
        msg.get("To", ""),
        msg.get("Cc", ""),
        msg.get("X-Mailing-List", ""),
        msg.get("X-BeenThere", ""),
    ]
    combined = " ".join(headers_to_check).lower()
    for pattern, canonical in LIST_MAP.items():
        if pattern.lower() in combined:
            return canonical
    return None


def extract_body(msg):
    """Extract plain text body, preferring text/plain."""
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
    """Return (iso_string, unix_ts) or ('', 0)."""
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
        sys.stderr.write(f"db error: {e}\n")


def harden():
    import platform, ctypes, ctypes.util
    if platform.system() != "OpenBSD":
        return
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.unveil(DB_PATH.encode(),                   b"rwc")
    libc.unveil(b"/var/db/mails/majordomo.log",     b"rwc")
    libc.unveil(b"/var/db/mails",                   b"rwc")
    libc.unveil(None, None)
    libc.pledge(b"stdio rpath wpath cpath flock", None)


def main():
    harden()
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    raw = sys.stdin.buffer.read()
    msg = email.message_from_bytes(raw)

    # Save majordomo confirmation emails to a separate file so we can act on them
    from_hdr = msg.get("From", "") + msg.get("Return-Path", "")
    if "majordomo" in from_hdr.lower():
        log_path = "/var/db/mails/majordomo.log"
        try:
            with open(log_path, "a") as f:
                f.write(f"\n{'='*60}\n")
                for h in ("From", "Return-Path", "Subject", "Date"):
                    f.write(f"{h}: {msg.get(h,'')}\n")
                f.write("\n" + extract_body(msg) + "\n")
        except Exception:
            pass
        conn.close()
        sys.exit(0)

    lst = extract_list(msg)
    if not lst:
        sys.stderr.write(
            f"processor: unrecognized list: from={msg.get('From','')} "
            f"list-id={msg.get('List-Id','')} "
            f"delivered-to={msg.get('Delivered-To','')} "
            f"subject={msg.get('Subject','')}\n"
        )
        conn.close()
        sys.exit(0)

    message_id = decode_header(msg.get("Message-Id", "")).strip("<>")
    if not message_id:
        conn.close()
        sys.exit(0)

    in_reply_to = decode_header(msg.get("In-Reply-To", "")).strip("<>") or None
    refs_raw = decode_header(msg.get("References", ""))
    refs = " ".join(r.strip("<>") for r in refs_raw.split()) if refs_raw else None

    subject = decode_header(msg.get("Subject", "(no subject)"))
    from_addr = decode_header(msg.get("From", ""))
    date_str, date_ts = parse_date(msg.get("Date", ""))
    body = extract_body(msg)

    insert(conn, (lst, message_id, in_reply_to, refs, subject, from_addr, date_str, date_ts, body))
    conn.close()


if __name__ == "__main__":
    main()
