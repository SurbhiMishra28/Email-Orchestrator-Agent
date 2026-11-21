"""IMAP inbox sync.

Fetches the newest messages with BODY.PEEK so nothing is marked read in the
user's mailbox, parses a short plain-text snippet and stores it locally.
"""
import email
import imaplib
import logging
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import List, Optional

from app.config import settings
from app.db import InboxMessage, Log, SessionLocal

logger = logging.getLogger(__name__)

MAX_SNIPPET = 600


class InboxNotConfigured(Exception):
    """Raised when IMAP credentials are missing."""


class InboxError(Exception):
    """Raised when the IMAP server cannot be read."""


def is_configured() -> bool:
    return bool(settings.IMAP_HOST and settings.IMAP_USER and settings.IMAP_PASSWORD)


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _text_of(message) -> str:
    if message.is_multipart():
        parts = message.walk()
    else:
        parts = [message]

    for part in parts:
        disposition = str(part.get("Content-Disposition") or "")
        if "attachment" in disposition.lower():
            continue
        if part.get_content_type() != "text/plain":
            continue
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")

    for part in parts:
        if part.get_content_type() != "text/html":
            continue
        payload = part.get_payload(decode=True) or b""
        html = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        return re.sub(r"<[^>]+>", " ", html)

    return ""


def _received_at(message) -> datetime:
    header = message.get("Date")
    if header:
        try:
            value = parsedate_to_datetime(header)
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def fetch_recent(limit: int = 25, after_uid: Optional[int] = None) -> List[dict]:
    """Fetch recent messages, or the next UID batch after ``after_uid``."""
    if not is_configured():
        raise InboxNotConfigured(
            "IMAP is not configured. Set IMAP_HOST, IMAP_USER and IMAP_PASS."
        )

    client = None
    try:
        client = imaplib.IMAP4_SSL(
            settings.IMAP_HOST, settings.IMAP_PORT, timeout=25
        )
        client.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise InboxError("Could not open the INBOX folder")

        if after_uid is None:
            status, data = client.uid("search", None, "ALL")
        else:
            status, data = client.uid("search", None, "UID", f"{after_uid + 1}:*")
        if status != "OK" or not data or not data[0]:
            return []

        all_uids = data[0].split()
        uids = all_uids[-limit:] if after_uid is None else all_uids[:limit]
        messages = []
        for uid in reversed(uids):
            status, parts = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            parsed = email.message_from_bytes(parts[0][1])
            snippet = " ".join(_text_of(parsed).split())[:MAX_SNIPPET]
            messages.append(
                {
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "sender": _decode(parsed.get("From"))[:320],
                    "subject": _decode(parsed.get("Subject"))[:500] or "(no subject)",
                    "snippet": snippet,
                    "received_at": _received_at(parsed),
                }
            )
        return messages
    except imaplib.IMAP4.error as exc:
        raise InboxError(f"IMAP authentication or fetch failed: {exc}") from exc
    except OSError as exc:
        raise InboxError(f"Could not reach the IMAP server: {exc}") from exc
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def sync_inbox(limit: int = 25, tenant_id: Optional[int] = None) -> dict:
    """Fetch messages and persist the ones not seen before."""
    db = SessionLocal()
    added = 0
    try:
        known_query = db.query(InboxMessage.uid)
        if tenant_id is not None:
            known_query = known_query.filter(InboxMessage.tenant_id == tenant_id)
        known_uids = known_query.all()
        numeric_uids = [
            int(row[0]) for row in known_uids
            if row[0] and str(row[0]).isdigit()
        ]
        fetched = fetch_recent(
            limit,
            after_uid=max(numeric_uids) if numeric_uids else None,
        )
        for item in fetched:
            exists_query = db.query(InboxMessage).filter(
                InboxMessage.uid == item["uid"]
            )
            if tenant_id is not None:
                exists_query = exists_query.filter(
                    InboxMessage.tenant_id == tenant_id
                )
            exists = exists_query.first()
            if exists:
                continue
            db.add(
                InboxMessage(
                    uid=item["uid"],
                    sender=item["sender"],
                    subject=item["subject"],
                    snippet=item["snippet"],
                    received_at=item["received_at"],
                    tenant_id=tenant_id,
                )
            )
            added += 1
        if added:
            db.add(
                Log(
                    message=f"Synced {added} inbox message(s)",
                    level="info",
                    tenant_id=tenant_id,
                )
            )
        db.commit()
        return {"fetched": len(fetched), "new": added}
    finally:
        db.close()
