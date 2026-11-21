"""SMTP delivery helpers shared by drafts, the queue and settings.

Every real send goes through :func:`send_email` so a draft can never be
marked "sent" without a configured, reachable SMTP server.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional, Tuple

from app.config import settings as app_settings


class MailNotConfigured(Exception):
    """Raised when SMTP settings are missing or incomplete."""


class MailDeliveryError(Exception):
    """Raised when the SMTP server rejects or drops the message."""


def _open_server(host: str, port: int, timeout: int = 30) -> smtplib.SMTP:
    """Open an SMTP connection, using implicit TLS on 465 and STARTTLS elsewhere."""
    context = ssl.create_default_context()
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

    if not getattr(smtp_config, "configured", False) or not host:
        raise MailNotConfigured(
            "SMTP is not configured. Add and test SMTP settings before sending."
        )
    if not sender:
        raise MailNotConfigured(
            "SMTP sender address is missing. Set a sender in Settings before sending."
        )
    if not recipient:
        raise MailDeliveryError("The recipient email address is missing.")

    # Use override values if provided, otherwise fall back to configured values
    final_sender = from_email or sender
    display_name = from_name or app_settings.SENDER_NAME or ""
    display_name = display_name.strip()
    message = EmailMessage()
    message["From"] = formataddr((display_name, final_sender)) if display_name else final_sender
    message["To"] = recipient
    message["Subject"] = subject or "(no subject)"
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
        # Get message-id before sending
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
