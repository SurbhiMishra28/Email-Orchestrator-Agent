"""Inbox sync using either Gmail API or IMAP.

Fetches the newest messages with BODY.PEEK so nothing is marked read in the
user's mailbox, parses a short plain-text snippet and stores it locally.

Resolution
----------
IMAP settings are stored per tenant in ``imap_config``. When ``gmail_api`` is
the selected transport, the local single-user tenant instead uses the OAuth
credentials from the process environment.
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
from app.db import IMAPConfig, InboxMessage, Log, SessionLocal
from app.services.mailer import active_transport, environment_fallback_allowed

logger = logging.getLogger(__name__)

MAX_SNIPPET = 600


class InboxNotConfigured(Exception):
    """Raised when IMAP credentials are missing."""


class InboxError(Exception):
    """Raised when the IMAP server cannot be read."""


class IMAPConfigView:
    """A resolved mailbox for inbox polling."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = 993,
        user: Optional[str] = None,
        password: Optional[str] = None,
        folder: Optional[str] = "INBOX",
        source: str = "database",
        api_mode: bool = False,
    ):
        self.host = (host or "").strip()
        try:
            self.port = int(port or 993)
        except (TypeError, ValueError):
            self.port = 993
        self.user = (user or "").strip()
        self.password = password or ""
        self.folder = (folder or "INBOX").strip() or "INBOX"
        self.source = source
        self.api_mode = api_mode

    @classmethod
    def from_row(cls, row, source: str = "database") -> "IMAPConfigView":
        if row is None:
            return cls(source=source)
        return cls(
            host=getattr(row, "host", None),
            port=getattr(row, "port", None),
            user=getattr(row, "user", None),
            password=getattr(row, "password", None),
            folder=getattr(row, "folder", None),
            source=source,
        )

    @property
    def configured(self) -> bool:
        if self.api_mode:
            from app.services.google_mail import config_from_settings

            return config_from_settings().configured
        return bool(self.host and self.user and self.password)

    def merged_with(self, fallback: "IMAPConfigView") -> "IMAPConfigView":
        return IMAPConfigView(
            host=self.host or fallback.host,
            port=self.port or fallback.port,
            user=self.user or fallback.user,
            password=self.password or fallback.password,
            folder=self.folder or fallback.folder,
            source="environment" if not self.host else self.source,
        )

    def describe(self) -> dict:
        """Public representation: never includes the password."""
        return {
            "host": self.host or None,
            "port": self.port,
            "user": self.user or None,
            "folder": self.folder,
            "configured": self.configured,
            "source": self.source,
            "transport": "gmail_api" if self.api_mode else "imap",
        }


def environment_config() -> IMAPConfigView:
    if active_transport() == "gmail_api":
        from app.services.google_mail import config_from_settings

        gmail = config_from_settings()
        return IMAPConfigView(
            port=443,
            user=gmail.user_email,
            source="environment",
            api_mode=True,
        )
    return IMAPConfigView(
        host=settings.IMAP_HOST,
        port=settings.IMAP_PORT,
        user=settings.IMAP_USER,
        password=settings.IMAP_PASSWORD,
        folder="INBOX",
        source="environment",
    )


def resolve_imap_config(db, tenant_id: Optional[int]) -> IMAPConfigView:
    """Return the IMAP mailbox to poll for ``tenant_id``.

    A stored row wins; its blanks are filled from the environment for the local
    single-user tenant only.
    """
    if active_transport() == "gmail_api":
        if environment_fallback_allowed(db, tenant_id):
            return environment_config()
        return IMAPConfigView()

    query = db.query(IMAPConfig)
    if tenant_id is not None:
        query = query.filter(IMAPConfig.tenant_id == tenant_id)
    row = query.order_by(IMAPConfig.id.asc()).first()

    view = IMAPConfigView.from_row(row)
    if view.configured:
        return view

    if environment_fallback_allowed(db, tenant_id):
        fallback = environment_config()
        if fallback.host:
            return view.merged_with(fallback)
    return view


def is_configured(tenant_id: Optional[int] = None) -> bool:
    """True when an IMAP mailbox is resolvable for ``tenant_id``.

    Called without a tenant it answers for the local/default mailbox, which is
    what the scheduler and health checks want.
    """
    db = SessionLocal()
    try:
        return resolve_imap_config(db, tenant_id).configured
    finally:
        db.close()


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


def _connect(config: IMAPConfigView, timeout: int = 25) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(config.host, config.port, timeout=timeout)
    client.login(config.user, config.password)
    return client


def test_connection(config: IMAPConfigView) -> dict:
    """Verify host reachability, credentials and that the folder opens."""
    if config.api_mode:
        from app.services.google_mail import test_connection as test_gmail_connection

        return test_gmail_connection()
    if not config.host:
        return {"ok": False, "message": "IMAP host is required"}
    if not config.user or not config.password:
        return {"ok": False, "message": "IMAP user and password are required"}
    if not 1 <= config.port <= 65535:
        return {"ok": False, "message": "IMAP port must be between 1 and 65535"}

    client = None
    try:
        client = _connect(config, timeout=15)
        status, _ = client.select(config.folder, readonly=True)
        if status != "OK":
            return {"ok": False, "message": f"Could not open folder '{config.folder}'"}
        return {"ok": True, "authenticated": True, "message": "Connection successful, authentication passed"}
    except imaplib.IMAP4.error as exc:
        return {"ok": False, "message": f"IMAP authentication failed: {exc}"}
    except OSError as exc:
        return {"ok": False, "message": f"Could not connect to {config.host}:{config.port} - {exc}"}
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def fetch_recent(
    limit: int = 25,
    after_uid: Optional[int] = None,
    tenant_id: Optional[int] = None,
    config: Optional[IMAPConfigView] = None,
) -> List[dict]:
    """Fetch recent messages, or the next UID batch after ``after_uid``."""
    if config is None:
        db = SessionLocal()
        try:
            config = resolve_imap_config(db, tenant_id)
        finally:
            db.close()

    if config.api_mode:
        return fetch_gmail_recent(limit, known_ids=set())

    if not config.configured:
        raise InboxNotConfigured(
            "Inbox is not configured. Add and test the selected mail transport before syncing."
        )

    client = None
    try:
        client = _connect(config)
        status, _ = client.select(config.folder, readonly=True)
        if status != "OK":
            raise InboxError("Could not open the INBOX folder")

        if after_uid is None:
            status, data = client.uid("search", None, "ALL")
        else:
            # ``UID n:*`` always returns the highest UID even when no message is
            # newer than n, which would re-fetch the last message on every poll.
            # Ask for the range explicitly and drop anything not above n.
            status, data = client.uid("search", None, "UID", f"{after_uid + 1}:*")
        if status != "OK" or not data or not data[0]:
            return []

        all_uids = [
            uid for uid in data[0].split()
            if after_uid is None
            or int(uid.decode() if isinstance(uid, bytes) else uid) > after_uid
        ]
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


def fetch_gmail_recent(limit: int, known_ids: set) -> List[dict]:
    """Fetch new inbox messages using Gmail message IDs as stable UIDs."""
    from app.services.google_mail import (
        GmailAPIError,
        config_from_settings,
        get_message_metadata,
        list_messages,
    )

    gmail = config_from_settings()
    if not gmail.configured:
        raise InboxNotConfigured(
            "Gmail API OAuth is not configured. Add the Gmail OAuth environment variables."
        )

    ids = []
    page_token = None
    page_limit = 500 if known_ids else max(1, min(limit, 500))
    try:
        for page_number in range(100):
            page = list_messages(
                gmail,
                max_results=page_limit,
                page_token=page_token,
            )
            found_known = False
            for item in page.get("messages", []):
                message_id = str(item.get("id") or "")
                if not message_id:
                    continue
                if message_id in known_ids:
                    found_known = True
                    break
                ids.append(message_id)
            if found_known:
                break
            page_token = page.get("nextPageToken")
            if not known_ids or not page_token:
                break
            if page_number == 99:
                raise InboxError(
                    "Gmail inbox has more than 50,000 unsynced messages; "
                    "sync again after reducing the backlog."
                )

        # Gmail lists newest first. On the first sync, keep the latest messages.
        # Later, process the oldest unseen batch first so the next sync can
        # continue toward the known-message boundary.
        if known_ids:
            ids = ids[-max(1, limit):]
        else:
            ids = ids[:max(1, limit)]
        messages = []
        for message_id in reversed(ids):
            message = get_message_metadata(gmail, message_id)
            payload = message.get("payload") or {}
            headers = {
                (header.get("name") or "").lower(): header.get("value") or ""
                for header in payload.get("headers", [])
            }
            try:
                received_at = datetime.fromtimestamp(
                    int(message.get("internalDate")) / 1000,
                    tz=timezone.utc,
                )
            except (TypeError, ValueError, OSError):
                received_at = datetime.now(timezone.utc)
            messages.append(
                {
                    "uid": message_id,
                    "sender": _decode(headers.get("from"))[:320],
                    "subject": _decode(headers.get("subject"))[:500] or "(no subject)",
                    "snippet": " ".join((message.get("snippet") or "").split())[
                        :MAX_SNIPPET
                    ],
                    "received_at": received_at,
                }
            )
        return messages
    except GmailAPIError as exc:
        raise InboxError(f"Gmail API inbox fetch failed: {exc}") from exc


def sync_inbox(limit: int = 25, tenant_id: Optional[int] = None, db=None) -> dict:
    """Fetch messages and persist the ones not seen before."""
    owns_session = db is None
    db = db or SessionLocal()
    added = 0
    try:
        config = resolve_imap_config(db, tenant_id)
        known_query = db.query(InboxMessage.uid)
        if tenant_id is not None:
            known_query = known_query.filter(InboxMessage.tenant_id == tenant_id)
        known_uids = known_query.all()
        if config.api_mode:
            fetched = fetch_gmail_recent(limit, {str(row[0]) for row in known_uids})
        else:
            numeric_uids = [
                int(row[0]) for row in known_uids
                if row[0] and str(row[0]).isdigit()
            ]
            fetched = fetch_recent(
                limit,
                after_uid=max(numeric_uids) if numeric_uids else None,
                tenant_id=tenant_id,
                config=config,
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
        if owns_session:
            db.close()
