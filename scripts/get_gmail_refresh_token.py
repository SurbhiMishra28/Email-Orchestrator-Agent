"""Authorize this app locally and print a Gmail OAuth refresh token."""
import base64
import hashlib
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.readonly"
)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        result = self.server.oauth_result

        if parsed.path != "/oauth2callback":
            self.send_error(404)
            return
        if params.get("state", [""])[0] != self.server.oauth_state:
            result["error"] = "OAuth state did not match"
            self.send_error(400)
            return

        error = params.get("error", [""])[0]
        if error:
            result["error"] = error
        else:
            result["code"] = params.get("code", [""])[0]

        body = (
            b"Authorization complete. You can close this browser tab and return "
            b"to the terminal."
        )
        self.send_response(200 if not error else 400)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def main() -> int:
    client_id = os.getenv("GMAIL_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit(
            "Set GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET first."
        )

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())

    server = HTTPServer(("127.0.0.1", 0), OAuthCallbackHandler)
    server.timeout = 1
    server.oauth_state = state
    server.oauth_result = {}
    redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth2callback"

    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    authorization_url = f"{AUTH_URL}?{query}"
    print("Opening Google sign-in in your browser...")
    if not webbrowser.open(authorization_url):
        print(f"Open this URL to authorize: {authorization_url}")

    deadline = time.monotonic() + 300
    try:
        while not server.oauth_result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    result = server.oauth_result
    if result.get("error"):
        raise SystemExit(f"Google authorization failed: {result['error']}")
    if not result.get("code"):
        raise SystemExit("Authorization timed out; run the script again.")

    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": result["code"],
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise SystemExit(f"Could not reach Google OAuth: {exc}") from exc

    if response.status_code >= 400:
        try:
            error = response.json().get("error_description") or response.json().get("error")
        except ValueError:
            error = response.text
        raise SystemExit(f"Google token exchange failed: {error}")

    payload = response.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise SystemExit(
            "Google returned no refresh token. Revoke this app's access from your "
            "Google Account and run the script again."
        )

    print("\nAdd these values to the backend deployment environment:")
    print(f"GMAIL_REFRESH_TOKEN={refresh_token}")
    print("Set GMAIL_USER_EMAIL to the Gmail account you just authorized.")
    print("Treat the refresh token like a password; do not commit or share it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
