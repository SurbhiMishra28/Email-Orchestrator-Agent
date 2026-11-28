"""HTTP Basic auth gate for the dashboard and API.

The app has no sign-in screen of its own: it runs one implicit workspace and
serves every request as that workspace. That is fine on localhost and hopeless
on a public URL, where the address book, the mailbox and the sending path are
all one unauthenticated request away.

Rather than introduce a user model the UI does not have, the whole surface is
put behind HTTP Basic auth. The browser prompts once and then sends the
credentials on every same-origin request, so the SPA keeps working unchanged.

The gate is disabled unless *both* credentials are configured, which keeps local
development and the test suite frictionless. Three route families are always
exempt, because they are not called by a browser holding credentials:

* ``/health`` -- the platform's readiness probe.
* ``/api/track/*`` -- the open pixel and click redirect, fetched by the
  recipient's mail client and browser.
* ``/api/cron/*`` -- driven by an external scheduler that authenticates with
  ``X-Cron-Secret`` instead.

Everything that is not under ``/api`` is exempt as well: the marketing page,
the sign-in page and the built SPA bundle are static files that must render
*before* any credential exists. The bundle holds no data; every value it shows
comes from the gated API. ``POST /api/auth/demo`` is public for the same reason
-- it is how a visitor obtains a session.

A valid ``Authorization: Bearer <jwt>`` is accepted alongside Basic, which is
what the sign-in page and the demo button use.
"""
import base64
import binascii
import hmac
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

REALM = "Email Orchestrator"

# Prefixes served without credentials. ``/api/track`` must be reachable by
# recipients, and ``/api/cron`` carries its own secret, so gating either would
# break open/click tracking and the scheduler respectively.
_EXEMPT_PREFIXES = (
    "/health",
    "/api/track",
    "/api/cron",
    "/api/auth/demo",
    "/favicon.ico",
)


def is_enabled() -> bool:
    """True when both credentials are set and the gate should be enforced."""
    return bool(
        (app_settings.BASIC_AUTH_USER or "").strip()
        and (app_settings.BASIC_AUTH_PASSWORD or "").strip()
    )


def is_exempt(path: str) -> bool:
    """True for routes that must answer without credentials.

    Anything outside ``/api`` is the static shell (marketing page, sign-in page,
    built assets, client-side routes such as ``/app``). It carries no tenant
    data, and it has to render before a credential exists.
    """
    normalized = path.rstrip("/") or "/"
    if not normalized.startswith("/api"):
        return True
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in _EXEMPT_PREFIXES
    )


def _bearer_is_valid(authorization: str) -> bool:
    """True when the header carries a JWT this process can verify.

    The sign-in page and the demo button exchange credentials for a token, so
    the gate has to accept it. An undecodable token is treated as absent rather
    than as a server error.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return False
    try:
        from jose import jwt

        from app.auth import ALGORITHM, SECRET_KEY

        payload = jwt.decode(token.strip(), SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub") is not None
    except Exception:  # any decode failure means "no valid token"
        return False


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Not authenticated"},
        headers={"WWW-Authenticate": f'Basic realm="{REALM}", charset="UTF-8"'},
    )


def _credentials_from_header(header: str) -> tuple[str, str] | None:
    """Decode an ``Authorization: Basic`` header into (user, password)."""
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    user, separator, password = decoded.partition(":")
    if not separator:
        return None
    return user, password


def install(app: FastAPI) -> bool:
    """Register the middleware. Returns whether the gate is active.

    Kept as an explicit call rather than an ``@app.middleware`` decorator so the
    tests can assert the gate is absent when no credentials are configured.
    """
    if not is_enabled():
        logger.info(
            "Basic auth not configured (set BASIC_AUTH_USER and "
            "BASIC_AUTH_PASSWORD to protect the dashboard)"
        )
        return False

    @app.middleware("http")
    async def require_basic_auth(request: Request, call_next):
        if is_exempt(request.url.path):
            return await call_next(request)

        provided = request.headers.get("authorization", "")
        if _bearer_is_valid(provided):
            return await call_next(request)

        credentials = _credentials_from_header(provided)

        expected_user = app_settings.BASIC_AUTH_USER.strip()
        expected_password = app_settings.BASIC_AUTH_PASSWORD

        # Two constant-time comparisons rather than one over a concatenated
        # string, so neither the user nor the password length leaks through the
        # comparison's timing.
        user_ok = credentials is not None and hmac.compare_digest(
            credentials[0], expected_user
        )
        password_ok = credentials is not None and hmac.compare_digest(
            credentials[1], expected_password
        )
        if not (user_ok and password_ok):
            return _unauthorized()

        return await call_next(request)

    logger.info("Basic auth enabled for user %r", app_settings.BASIC_AUTH_USER)
    return True