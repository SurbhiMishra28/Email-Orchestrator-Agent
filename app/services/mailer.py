"""SMTP delivery helpers shared by drafts, the queue and settings.

Every real send goes through :func:`send_email` so a draft can never be
marked "sent" without a configured, reachable SMTP server.

Resolution order
----------------
A tenant's SMTP settings live in the database so each workspace can have its own
mailbox. A row can be blank, though -- a tenant provisioned before SMTP was
per-tenant, or one whose fields were cleared -- and a blank row used to report
"SMTP is not configured" forever even though the deployment's ``.env`` held a
working mailbox.

:func:`resolve_smtp_config` therefore merges the stored row with the
environment, but *only* for the implicit local tenant of this single-user app.
A second tenant created through the API never inherits the operator's mailbox,
so the credentials in ``.env`` stay with the workspace that owns them.

Outbound transport
------------------
SMTP is the default and works everywhere SMTP is reachable. When
``RESEND_API_KEY`` is set the app talks to Resend's REST API over HTTPS instead.
That matters on hosts that block SMTP ports -- Render's free tier blocks 25/465/
587, so a Gmail mailbox cannot leave the box there. Resend speaks the same
message body and returns the same message-id shape, so callers see no
difference; only the transport changes.
"""
import json
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Dict, Optional, Tuple

import httpx

from app.config import settings as app_settings

# A subject is a single header line. Keeping well under the 998 octet limit
# leaves room for folding and avoids a relay-side truncation.
SUBJECT_MAX_LENGTH = 250

# Resend's REST endpoint. HTTPS on 443, which every host allows for web
# traffic, so it bypasses SMTP port blocks entirely.
RESEND_API_URL = "https://api.resend.com/emails"

# How long to wait for the Resend API before giving up. Kept short: a send
# that cannot complete in 15s is not going to complete in 15m either.
RESEND_TIMEOUT_SECONDS = 15


class MailNotConfigured(Exception):
    """Raised when SMTP settings are missing or incomplete."""


class MailDeliveryError(Exception):
    """Raised when the SMTP server rejects or drops the message."""


def sanitize_subject(subject: str, max_length: int = SUBJECT_MAX_LENGTH) -> str:
    """Return ``subject`` as a single, quote-free header line.

    AI-generated subjects routinely arrive wrapped in quotes, prefixed with
    markdown or spread over several lines. A line break in a header raises in
    ``EmailMessage``, so the value has to be flattened before it is set.
    """
    text = " ".join(str(subject or "").split())
    text = text.strip().strip("`*_").strip().strip("\"'").strip()
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text or "(no subject)"


class SMTPConfigView:
    """A resolved mailbox: either the tenant's row or the local environment.

    Callers only read attributes, so this mirrors the columns of the
    ``SMTPConfig`` model plus ``source``, which tells the UI where the values
    came from (``database`` or ``environment``).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = 587,
        user: Optional[str] = None,
        password: Optional[str] = None,
        sender: Optional[str] = None,
        source: str = "database",
    ):
        self.host = (host or "").strip()
        try:
            self.port = int(port or 587)
        except (TypeError, ValueError):
            self.port = 587
        self.user = (user or "").strip()
        self.password = password or ""
        self.sender = (sender or "").strip()
        self.source = source

    @classmethod
    def from_row(cls, row, source: str = "database") -> "SMTPConfigView":
        if row is None:
            return cls(source=source)
        return cls(
            host=getattr(row, "host", None),
            port=getattr(row, "port", None),
            user=getattr(row, "user", None),
            password=getattr(row, "password", None),
            sender=getattr(row, "sender", None),
            source=source,
        )

    @property
    def configured(self) -> bool:
        return bool(self.host and (self.sender or self.user))

    @property
    def authentication_configured(self) -> bool:
        return bool(self.user and self.password)

    def merged_with(self, fallback: "SMTPConfigView") -> "SMTPConfigView":
        """Fill this view's blanks from ``fallback``, keeping any saved value."""
        return SMTPConfigView(
            host=self.host or fallback.host,
            port=self.port or fallback.port,
            user=self.user or fallback.user,
            password=self.password or fallback.password,
            sender=self.sender or fallback.sender,
            source="environment" if not self.host else self.source,
        )

    def describe(self) -> Dict[str, object]:
        """Public representation: never includes the password."""
        return {
            "host": self.host or None,
            "port": self.port,
            "user": self.user or None,
            "sender": self.sender or None,
            "configured": self.configured,
            "authentication_configured": self.authentication_configured,
            "source": self.source,
        }


def environment_config() -> SMTPConfigView:
    """The mailbox configured in the process environment."""
    sender = app_settings.DEFAULT_SMTP_SENDER or app_settings.DEFAULT_SMTP_USER
    return SMTPConfigView(
        host=app_settings.DEFAULT_SMTP_HOST,
        port=app_settings.DEFAULT_SMTP_PORT,
        user=app_settings.DEFAULT_SMTP_USER,
        password=app_settings.DEFAULT_SMTP_PASSWORD,
        sender=sender,
        source="environment",
    )


def local_tenant_id(db) -> Optional[int]:
    """Return the id of the implicit single-user tenant, if there is one.

    The local tool provisions exactly one tenant at startup and every
    unauthenticated request is attributed to it, so the lowest id is that
    tenant. ``None`` means the database is still empty.
    """
    from app.db import Tenant

    row = db.query(Tenant.id).order_by(Tenant.id.asc()).first()
    return int(row[0]) if row else None


def environment_fallback_allowed(db, tenant_id: Optional[int]) -> bool:
    """True only for the implicit local tenant.

    This is the boundary that keeps the operator's ``.env`` mailbox with the
    workspace that owns it: a second tenant created through the API can never
    resolve to it, even if it happens to hold a low id.
    """
    if not app_settings.SINGLE_USER_MODE:
        return False
    if tenant_id is None:
        return True
    return tenant_id == local_tenant_id(db)


def resolve_smtp_config(db, tenant_id: Optional[int]) -> SMTPConfigView:
    """Return the SMTP settings to use for ``tenant_id``.

    The stored row wins. Blank or partial rows are completed from the
    environment for the local tenant only, which is what keeps a fresh install
    (or a row reset in Settings) sending instead of reporting "not configured".
    """
    from app.db import SMTPConfig

    query = db.query(SMTPConfig)
    if tenant_id is not None:
        query = query.filter(SMTPConfig.tenant_id == tenant_id)
    row = query.order_by(SMTPConfig.id.asc()).first()

    view = SMTPConfigView.from_row(row)
    if view.configured and view.authentication_configured:
        return view

    if environment_fallback_allowed(db, tenant_id):
        fallback = environment_config()
        if fallback.host:
            merged = view.merged_with(fallback)
            # A host taken from the environment is not saved, so it must not be
            # reported as a stored database value.
            if not view.host:
                merged.source = "environment"
            return merged
    return view


def _open_server(host: str, port: int, timeout: int = 30) -> smtplib.SMTP:
    """Open an SMTP connection, using implicit TLS on 465 and STARTTLS elsewhere.

    Transient network errors (``Network is unreachable``, ``Connection reset``,
    ``Temporary failure in name resolution``) are retried a few times with a
    short backoff, because a relay that answers one moment may be unreachable
    the next on a flaky link. Each attempt resolves the host fresh so an
    IPv4/IPv6 flip gets a chance to land on a working address.
    """
    context = ssl.create_default_context()
    last_exc: Optional[OSError] = None
    for attempt in range(3):
        try:
            if port == 465:
                return smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)

            server = smtplib.SMTP(host, port, timeout=timeout)
            try:
                server.ehlo()
                if port == 587 or server.has_extn("starttls"):
                    server.starttls(context=context)
                    server.ehlo()
            except Exception:
                server.close()
                raise
            return server
        except (OSError, smtplib.SMTPException) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    # Unreachable: the loop always returns or raises.
    raise last_exc if last_exc else OSError("Could not open SMTP connection")


def _close_server(server: smtplib.SMTP) -> None:
    try:
        server.quit()
    except Exception:
        try:
            server.close()
        except Exception:
            pass


def _connection_parts(smtp_config) -> Tuple[str, int, Optional[str], Optional[str], str]:
    host = (getattr(smtp_config, "host", None) or "").strip()
    try:
        port = int(getattr(smtp_config, "port", None) or 587)
    except (TypeError, ValueError):
        port = 587
    user = (getattr(smtp_config, "user", None) or "").strip() or None
    password = getattr(smtp_config, "password", None) or None
    sender = (getattr(smtp_config, "sender", None) or user or "").strip()
    return host, port, user, password, sender


def is_configured(smtp_config) -> bool:
    """True when a host and sender address are available."""
    host, _port, _user, _password, sender = _connection_parts(smtp_config)
    return bool(host and sender)


def send_email(smtp_config, recipient: str, subject: str, body: str, from_name: Optional[str] = None, from_email: Optional[str] = None, html_body: Optional[str] = None) -> str:
    """Send an email, raising a clear error when that is impossible.

    ``body`` is always sent as the plain-text part. ``html_body`` is optional and
    only supplied when a tenant opted into engagement tracking, in which case the
    message becomes ``multipart/alternative`` with both parts.

    Returns the message-id of the sent email.
    """
    host, port, user, password, sender = _connection_parts(smtp_config)

    configured = (
        getattr(smtp_config, "configured", None)
        if getattr(smtp_config, "configured", None) is not None
        else is_configured(smtp_config)
    )
    if not configured or not host:
        raise MailNotConfigured(
            "SMTP is not configured. Add and test SMTP settings before sending."
        )
    if not sender:
        raise MailNotConfigured(
            "SMTP sender address is missing. Set a sender in Settings before sending."
        )
    if not recipient:
        raise MailDeliveryError("The recipient email address is missing.")

    if app_settings.MAIL_SUPPRESS_SEND:
        # Dry-run: the message is never handed to a relay. Recorded as delivered
        # so callers can exercise the full pipeline without mailing anyone.
        return f"<suppressed-{uuid.uuid4().hex}@localhost>"

    # Use override values if provided, otherwise fall back to configured values
    final_sender = from_email or sender
    display_name = from_name or app_settings.SENDER_NAME or ""
    display_name = display_name.strip()

    # Gmail API over HTTPS, used when the OAuth settings are present and the
    # mailbox resolved to the Gmail marker host.
    from app.services import gmail_api

    if gmail_api.is_gmail_host(host):
        message = EmailMessage()
        # Gmail always sends as the authenticated mailbox, so use that address.
        gmail_sender = app_settings.GMAIL_USER
        message["From"] = formataddr((display_name, gmail_sender)) if display_name else gmail_sender
        message["To"] = recipient
        message["Subject"] = sanitize_subject(subject)
        message["Message-ID"] = make_msgid(domain=gmail_sender.rpartition("@")[2] or None)
        message["Date"] = formatdate(localtime=False)
        message["List-Unsubscribe"] = f"<mailto:{gmail_sender}?subject=unsubscribe>"
        message.set_content(body or "")
        if html_body:
            message.add_alternative(html_body, subtype="html")
        try:
            gmail_api.send_raw(message.as_bytes())
        except gmail_api.GmailError as exc:
            raise MailDeliveryError(str(exc)) from exc
        return message["Message-ID"]

    # Resend REST API over HTTPS. Used when RESEND_API_KEY is set, which is the
    # only way to send from hosts that block SMTP ports (Render free tier).
    if app_settings.RESEND_API_KEY:
        return _send_via_resend(
            final_sender=final_sender,
            display_name=display_name,
            recipient=recipient,
            subject=sanitize_subject(subject),
            body=body or "",
            html_body=html_body,
        )

    message = EmailMessage()
    message["From"] = formataddr((display_name, final_sender)) if display_name else final_sender
    message["To"] = recipient
    message["Subject"] = sanitize_subject(subject)
    # A Message-ID and Date are what make replies thread correctly and what
    # receiving servers use to de-duplicate. Reading Message-ID after the fact
    # returns None, so both headers are set before the send.
    domain = final_sender.rpartition("@")[2] or None
    message["Message-ID"] = make_msgid(domain=domain)
    message["Date"] = formatdate(localtime=False)
    # Compliance: give recipients a way to opt out of further mail.
    message["List-Unsubscribe"] = f"<mailto:{final_sender}?subject=unsubscribe>"
    message.set_content(body or "")
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        server = _open_server(host, port)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError(f"Could not connect to {host}:{port} - {exc}") from exc

    try:
        if user and password:
            server.login(user, password)
        msg_id = message["Message-ID"]
        server.send_message(message)
        return msg_id
    except smtplib.SMTPAuthenticationError as exc:
        raise MailDeliveryError(f"SMTP authentication failed: {exc}") from exc
    except smtplib.SMTPException as exc:
        raise MailDeliveryError(f"SMTP error: {exc}") from exc
    except OSError as exc:
        raise MailDeliveryError(f"SMTP connection failed: {exc}") from exc
    finally:
        _close_server(server)


def _send_via_resend(
    final_sender: str,
    display_name: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: Optional[str],
) -> str:
    """Send one message through Resend's REST API and return its message-id.

    HTTPS on 443, so it works on hosts that block SMTP ports. Resend returns a
    JSON id like ``<msg-id@resend.com>``; we pass it through unchanged so the
    tracking layer sees the same shape an SMTP send would produce.
    """
    from_addr = formataddr((display_name, final_sender)) if display_name else final_sender
    payload: Dict[str, object] = {
        "from": from_addr,
        "to": recipient,
        "subject": subject,
        "text": body,
    }
    if html_body:
        payload["html"] = html_body

    headers = {
        "Authorization": f"Bearer {app_settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=RESEND_TIMEOUT_SECONDS) as client:
            resp = client.post(RESEND_API_URL, headers=headers, content=json.dumps(payload))
    except httpx.HTTPError as exc:
        raise MailDeliveryError(f"Resend API request failed: {exc}") from exc

    if resp.status_code >= 400:
        # Resend returns a JSON body with ``name``/``message`` describing the
        # failure; surface the message rather than the raw status line.
        try:
            detail = resp.json()
            message = detail.get("message") or detail.get("name") or resp.text
        except Exception:
            message = resp.text or f"HTTP {resp.status_code}"
        raise MailDeliveryError(f"Resend rejected the message: {message}")

    try:
        data = resp.json()
    except Exception as exc:
        raise MailDeliveryError(f"Resend returned invalid JSON: {exc}") from exc

    msg_id = data.get("id") or ""
    if not msg_id:
        raise MailDeliveryError("Resend returned no message id")
    return msg_id


def test_connection(
    host: Optional[str],
    port: Optional[int],
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> dict:
    """Check connectivity and, when credentials are supplied, authentication."""
    host = (host or "").strip()
    if not host:
        return {"ok": False, "message": "SMTP host is required"}

    try:
        port = int(port or 587)
    except (TypeError, ValueError):
        return {"ok": False, "message": "SMTP port must be a number"}

    if not 1 <= port <= 65535:
        return {"ok": False, "message": "SMTP port must be between 1 and 65535"}

    try:
        server = _open_server(host, port, timeout=10)
    except smtplib.SMTPAuthenticationError as exc:
        return {"ok": True, "authenticated": False, "message": f"Connected, but authentication failed: {exc}"}
    except ssl.SSLError as exc:
        return {"ok": False, "message": f"TLS handshake failed: {exc}"}
    except (OSError, smtplib.SMTPException) as exc:
        return {"ok": False, "message": f"Could not connect to {host}:{port} - {exc}"}

    try:
        if user and password:
            try:
                server.login(user, password)
                return {
                    "ok": True,
                    "authenticated": True,
                    "message": "Connection successful, authentication passed",
                }
            except smtplib.SMTPAuthenticationError as exc:
                return {
                    "ok": True,
                    "authenticated": False,
                    "message": f"Connection successful, but authentication failed: {exc}",
                }
            except (OSError, smtplib.SMTPException) as exc:
                return {
                    "ok": True,
                    "authenticated": False,
                    "message": f"Connection successful, but authentication error: {exc}",
                }
        return {"ok": True, "authenticated": True, "message": "Connection test successful"}
    finally:
        _close_server(server)
