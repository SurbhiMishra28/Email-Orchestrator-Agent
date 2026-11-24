"""Gmail API transport: send and read mail over HTTPS (port 443).

Used when GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN and
GMAIL_USER are all set. Works on hosts that block SMTP/IMAP ports. The refresh
token must be granted the ``gmail.send`` and ``gmail.readonly`` scopes.
"""
import base64
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from app.config import settings

MARKER_HOST = "gmail.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
TIMEOUT = 20

_lock = threading.Lock()
_token: Dict[str, object] = {"value": "", "expires": 0.0}


class GmailError(Exception):
    """Raised when Google rejects a request or cannot be reached."""


def enabled() -> bool:
    return bool(settings.GMAIL_API_ENABLED)


def is_gmail_host(host: Optional[str]) -> bool:
    return enabled() and (host or "").strip().lower() == MARKER_HOST


def _error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error")
        if isinstance(err, dict):
            return err.get("message") or str(err)
        return data.get("error_description") or str(err or resp.text)
    except Exception:
        return resp.text or f"HTTP {resp.status_code}"


def access_token() -> str:
    with _lock:
        if _token["value"] and float(_token["expires"]) > time.time() + 60:
            return str(_token["value"])
        try:
            resp = httpx.post(
                TOKEN_URL,
                data={
                    "client_id": settings.GMAIL_CLIENT_ID,
                    "client_secret": settings.GMAIL_CLIENT_SECRET,
                    "refresh_token": settings.GMAIL_REFRESH_TOKEN,
                    "grant_type": "refresh_token",
                },
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise GmailError(f"Could not reach Google OAuth: {exc}") from exc
        if resp.status_code >= 400:
            raise GmailError(f"Google rejected the refresh token: {_error_text(resp)}")
        data = resp.json()
        _token["value"] = data["access_token"]
        _token["expires"] = time.time() + int(data.get("expires_in", 3600))
        return str(_token["value"])


def _request(method: str, path: str, **kwargs) -> dict:
    try:
        resp = httpx.request(
            method,
            f"{API}{path}",
            headers={"Authorization": f"Bearer {access_token()}"},
            timeout=TIMEOUT,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise GmailError(f"Gmail API request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise GmailError(f"Gmail API error {resp.status_code}: {_error_text(resp)}")
    return resp.json()


def send_raw(raw_message: bytes) -> str:
    """Send an RFC 822 message as the authenticated mailbox; return its Gmail id."""
    encoded = base64.urlsafe_b64encode(raw_message).decode()
    data = _request("POST", "/messages/send", json={"raw": encoded})
    msg_id = data.get("id")
    if not msg_id:
        raise GmailError("Gmail API returned no message id")
    return msg_id


def test_connection() -> dict:
    try:
        profile = _request("GET", "/profile")
    except GmailError as exc:
        return {"ok": False, "message": str(exc)}
    return {
        "ok": True,
        "authenticated": True,
        "message": f"Gmail API connected as {profile.get('emailAddress', settings.GMAIL_USER)}",
    }


def fetch_recent(limit: int = 25) -> List[dict]:
    """Newest inbox messages in the shape ``inbox.fetch_recent`` returns."""
    listing = _request("GET", "/messages", params={"labelIds": "INBOX", "maxResults": limit})
    messages = []
    for ref in listing.get("messages", []):
        m = _request(
            "GET",
            f"/messages/{ref['id']}",
            params=[
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
            ],
        )
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        received = datetime.fromtimestamp(int(m.get("internalDate", 0)) / 1000, tz=timezone.utc)
        messages.append(
            {
                "uid": m["id"],
                "sender": headers.get("from", "")[:320],
                "subject": headers.get("subject", "")[:500] or "(no subject)",
                "snippet": (m.get("snippet") or "")[:600],
                "received_at": received,
            }
        )
    return messages
