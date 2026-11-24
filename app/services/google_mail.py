"""Gmail API client using deployment-provided OAuth refresh credentials."""
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import httpx

from app.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
REQUEST_TIMEOUT_SECONDS = 20
TOKEN_REFRESH_MARGIN_SECONDS = 60


class GmailAPIError(Exception):
    """Raised when Google OAuth or the Gmail API rejects a request."""


@dataclass(frozen=True)
class GmailOAuthConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    user_email: str

    @property
    def configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.refresh_token
            and self.user_email
        )


_token_cache: Dict[Tuple[str, str, str], Tuple[str, float]] = {}
_token_lock = threading.Lock()


def config_from_settings() -> GmailOAuthConfig:
    return GmailOAuthConfig(
        client_id=(settings.GMAIL_OAUTH_CLIENT_ID or "").strip(),
        client_secret=(settings.GMAIL_OAUTH_CLIENT_SECRET or "").strip(),
        refresh_token=(settings.GMAIL_REFRESH_TOKEN or "").strip(),
        user_email=(settings.GMAIL_USER_EMAIL or "").strip(),
    )


def _response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("status") or error)
    if error:
        return str(payload.get("error_description") or error)
    return str(payload.get("error_description") or response.text or f"HTTP {response.status_code}")


def _access_token(config: GmailOAuthConfig, force_refresh: bool = False) -> str:
    if not config.configured:
        raise GmailAPIError(
            "Gmail API OAuth is not configured. Set GMAIL_OAUTH_CLIENT_ID, "
            "GMAIL_OAUTH_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, and GMAIL_USER_EMAIL."
        )

    key = (config.client_id, config.client_secret, config.refresh_token)
    now = time.monotonic()
    with _token_lock:
        cached = _token_cache.get(key)
        if (
            not force_refresh
            and cached
            and cached[1] > now + TOKEN_REFRESH_MARGIN_SECONDS
        ):
            return cached[0]

        try:
            response = httpx.post(
                TOKEN_URL,
                data={
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "refresh_token": config.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GmailAPIError(f"Could not reach Google OAuth: {exc}") from exc

        if response.status_code >= 400:
            raise GmailAPIError(
                f"Google OAuth token refresh failed: {_response_error(response)}"
            )

        try:
            payload = response.json()
            token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError) as exc:
            raise GmailAPIError("Google OAuth returned an invalid token response") from exc

        _token_cache[key] = (token, now + max(0, expires_in))
        return token


def api_request(
    config: GmailOAuthConfig,
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> dict:
    """Call the Gmail API, refreshing once if a cached access token was revoked."""
    url = f"{API_BASE_URL}/{path.lstrip('/')}"
    for attempt in range(2):
        token = _access_token(config, force_refresh=attempt > 0)
        try:
            response = httpx.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                json=json_body,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GmailAPIError(f"Gmail API request failed: {exc}") from exc

        if response.status_code == 401 and attempt == 0:
            continue
        if response.status_code >= 400:
            raise GmailAPIError(
                f"Gmail API returned HTTP {response.status_code}: "
                f"{_response_error(response)}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise GmailAPIError("Gmail API returned invalid JSON") from exc

    raise GmailAPIError("Gmail API authorization failed after refreshing the token")


def test_connection(config: Optional[GmailOAuthConfig] = None) -> dict:
    """Validate OAuth and confirm the authorized Gmail mailbox."""
    config = config or config_from_settings()
    if not config.configured:
        return {
            "ok": False,
            "message": (
                "Set GMAIL_OAUTH_CLIENT_ID, GMAIL_OAUTH_CLIENT_SECRET, "
                "GMAIL_REFRESH_TOKEN, and GMAIL_USER_EMAIL."
            ),
        }

    try:
        profile = api_request(config, "GET", "users/me/profile")
    except GmailAPIError as exc:
        return {"ok": False, "message": str(exc)}

    authorized_email = (profile.get("emailAddress") or "").strip()
    if authorized_email.lower() != config.user_email.lower():
        return {
            "ok": False,
            "message": (
                "GMAIL_USER_EMAIL must match the Gmail account that authorized "
                "the OAuth credentials."
            ),
        }
    return {
        "ok": True,
        "authenticated": True,
        "email": authorized_email,
        "message": f"Gmail API connected as {authorized_email}",
    }


def send_raw_message(config: GmailOAuthConfig, raw_message: str) -> dict:
    """Submit a base64url-encoded RFC 2822 message to the Gmail API."""
    return api_request(
        config,
        "POST",
        "users/me/messages/send",
        json_body={"raw": raw_message},
    )


def list_messages(
    config: GmailOAuthConfig,
    *,
    max_results: int,
    page_token: Optional[str] = None,
    query: str = "in:inbox",
) -> dict:
    params = {"q": query, "maxResults": max_results}
    if page_token:
        params["pageToken"] = page_token
    return api_request(config, "GET", "users/me/messages", params=params)


def get_message_metadata(config: GmailOAuthConfig, message_id: str) -> dict:
    return api_request(
        config,
        "GET",
        f"users/me/messages/{message_id}",
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "Subject", "Date"],
        },
    )
