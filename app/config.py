"""Application configuration with environment variable support."""
import os
from typing import Optional

from dotenv import load_dotenv

# Load the project-level .env before any setting below reads the environment.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


def _platform_public_url() -> str:
    """Return the public origin a hosting platform assigned, if any.

    Render, Railway, Fly and Vercel each expose the deployed URL under a
    different variable. Reading them here means tracking links and CORS work on
    a fresh deploy without anyone copying a URL into the environment by hand,
    which is the mistake that silently produces click links pointing at
    localhost.

    Vercel is checked first because ``VERCEL_URL`` is a host without a scheme
    (``my-app.vercel.app``) and ``VERCEL_PROJECT_PRODUCTION_URL`` is the stable
    production alias that survives preview deployments.
    """
    production_url = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
    if production_url:
        return _with_scheme(production_url)

    vercel_url = os.getenv("VERCEL_URL", "").strip()
    if vercel_url:
        return _with_scheme(vercel_url)

    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if render_url:
        return render_url.rstrip("/")

    domains = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domains:
        domain = domains.split(",")[0].strip()
        if domain and not domain.startswith("http"):
            domain = f"https://{domain}"
        return domain.rstrip("/")

    fly_host = os.getenv("FLY_APP_NAME", "").strip()
    if fly_host:
        return f"https://{fly_host}.fly.dev"

    return ""


def _with_scheme(host: str) -> str:
    """Prefix a bare platform hostname with https:// and drop any trailing slash."""
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host.rstrip("/")


_PLATFORM_PUBLIC_URL = _platform_public_url()


class Settings:
    """Application settings loaded from environment variables with defaults."""
    
    # Default goal for email orchestration
    DEFAULT_GOAL: str = os.getenv("GOAL") or os.getenv(
        "DEFAULT_GOAL", "book intro calls with sales leaders"
    )
    
    # Default business information
    DEFAULT_BUSINESS_NAME: str = os.getenv("DEFAULT_BUSINESS_NAME", "")
    DEFAULT_BUSINESS_OFFER: str = os.getenv("DEFAULT_BUSINESS_OFFER", "")
    
    # Email sending limits
    DEFAULT_DAILY_CAP: int = int(
        os.getenv("DAILY_CAP") or os.getenv("DEFAULT_DAILY_CAP", "50")
    )
    DEFAULT_DOMAIN_CAP: int = int(
        os.getenv("DOMAIN_CAP") or os.getenv("DEFAULT_DOMAIN_CAP", "3")
    )

    # Automation flags
    DEFAULT_AUTO_APPROVE: bool = (
        os.getenv("AUTO_APPROVE") or os.getenv("DEFAULT_AUTO_APPROVE", "false")
    ).lower() == "true"
    DEFAULT_AUTOPILOT: bool = (
        os.getenv("AUTOPILOT") or os.getenv("DEFAULT_AUTOPILOT", "false")
    ).lower() == "true"
    
    # Database
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    
    # SMTP defaults (SMTP_* is the documented name, DEFAULT_SMTP_* the legacy alias)
    DEFAULT_SMTP_HOST: str = os.getenv("SMTP_HOST") or os.getenv("DEFAULT_SMTP_HOST", "")
    DEFAULT_SMTP_PORT: int = int(os.getenv("SMTP_PORT") or os.getenv("DEFAULT_SMTP_PORT", "587"))
    DEFAULT_SMTP_USER: str = os.getenv("SMTP_USER") or os.getenv("DEFAULT_SMTP_USER", "")
    DEFAULT_SMTP_PASSWORD: str = os.getenv("SMTP_PASS") or os.getenv("DEFAULT_SMTP_PASSWORD", "")
    DEFAULT_SMTP_SENDER: str = (
        os.getenv("SMTP_FROM")
        or os.getenv("SMTP_SENDER")
        or os.getenv("DEFAULT_SMTP_SENDER", "")
    )
    SENDER_NAME: str = os.getenv("SENDER_NAME", "")

    # IMAP inbox polling
    IMAP_HOST: str = os.getenv("IMAP_HOST", "")
    IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USER: str = os.getenv("IMAP_USER", "")
    IMAP_PASSWORD: str = os.getenv("IMAP_PASS") or os.getenv("IMAP_PASSWORD", "")
    IMAP_POLL_MINUTES: int = int(os.getenv("IMAP_POLL_MINUTES", "10"))

    # Gmail API OAuth credentials. These are deployment secrets and are never
    # stored in tenant configuration rows or returned by status endpoints.
    GMAIL_OAUTH_CLIENT_ID: str = os.getenv("GMAIL_OAUTH_CLIENT_ID", "")
    GMAIL_OAUTH_CLIENT_SECRET: str = os.getenv("GMAIL_OAUTH_CLIENT_SECRET", "")
    GMAIL_REFRESH_TOKEN: str = os.getenv("GMAIL_REFRESH_TOKEN", "")
    GMAIL_USER_EMAIL: str = os.getenv("GMAIL_USER_EMAIL", "")

    # Follow-up drafting (never sends on its own)
    FOLLOWUPS_ENABLED: bool = os.getenv("FOLLOWUPS_ENABLED", "true").lower() == "true"

    # Refuse to send to addresses that cannot be real mailboxes (reserved
    # domains such as example.com, disposable inboxes, mail system mailboxes).
    # Enabled by default because the pipeline sends unattended; tests turn it
    # off because they intentionally use example.com recipients.
    BLOCK_PLACEHOLDER_RECIPIENTS: bool = (
        os.getenv("BLOCK_PLACEHOLDER_RECIPIENTS", "true").lower() == "true"
    )

    # Dry-run mode: every send is recorded as successful without opening an SMTP
    # connection. Used by the test suite (which would otherwise mail the real
    # account configured in .env) and by staging deployments.
    MAIL_SUPPRESS_SEND: bool = (
        os.getenv("MAIL_SUPPRESS_SEND", "false").lower() == "true"
    )

    # Absolute origin used to build open-pixel and click-tracking URLs. It must
    # be reachable by recipients, so a public deployment sets it explicitly;
    # the platform's own URL is used when one is present, and the default keeps
    # local development working.
    PUBLIC_BASE_URL: str = (
        os.getenv("PUBLIC_BASE_URL") or _PLATFORM_PUBLIC_URL or "http://localhost:8000"
    )

    # How many queue passes one process may run at once. Sending is still
    # serialized per tenant by the pacing rule in ``services/limits.py``; this
    # bounds how much work a burst of async submissions can start.
    SEND_CONCURRENCY: int = int(os.getenv("SEND_CONCURRENCY", "2"))

    # APScheduler jobs (inbox polling + autopilot) need a process that stays
    # alive between requests. Serverless hosts cannot provide that: each
    # invocation starts and is frozen, so a scheduler registered at startup
    # never fires and the send worker loses its thread between requests. Set
    # this to false on such hosts and drive the same work from an external
    # cron hitting POST /api/scheduling/run-now, or from a long-lived host.
    ENABLE_BACKGROUND_JOBS: bool = (
        os.getenv("ENABLE_BACKGROUND_JOBS", "true").lower() == "true"
    )
    
    # CORS - loopback origins by default; wildcard + credentials is invalid.
    # The platform-assigned origin is appended so a fresh deploy can call its
    # own API from the browser without extra configuration.
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,"
        "http://127.0.0.1:5173,http://localhost:5173"
        + (f",{_PLATFORM_PUBLIC_URL}" if _PLATFORM_PUBLIC_URL else ""),
    )
    
    # NVIDIA API
    NVIDIA_API_KEY: Optional[str] = os.getenv("NVIDIA_API_KEY")
    NVIDIA_MODEL: str = os.getenv(
        "NVIDIA_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"
    )
    
    # Frontend
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:8000")

    # JWT Settings for the programmatic API
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Resend email API (https://resend.com). When this key is set, send_email()
    # talks to Resend's REST API over HTTPS instead of SMTP. That matters on
    # hosts that block SMTP ports -- Render's free tier blocks 25/465/587, so a
    # Gmail mailbox cannot leave the box there. Resend uses the same message
    # body and returns the same message-id shape, so callers see no difference;
    # only the transport changes. Leave blank to send over SMTP.
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY")
    RESEND_FROM: str = os.getenv("RESEND_FROM", "")

    # Which outbound transport to use: "smtp", "resend", "gmail_api", or "auto".
    #
    # ``auto`` keeps the original behaviour (Resend whenever a key is present)
    # and is the default for compatibility. It is the wrong choice for an
    # account whose Resend domains are unverified: Resend rejects a gmail.com
    # From address with a 403, so every send fails even though a working SMTP
    # mailbox is configured. Setting the transport explicitly makes delivery
    # depend on this setting rather than on whether a key happens to be present.
    MAIL_TRANSPORT: str = (
        os.getenv("MAIL_TRANSPORT", "auto") or "auto"
    ).strip().lower()

    # External cron entrypoint (``POST /api/cron/tick``). The dashboard URL is
    # public and the app has no login screen, so the cron route authenticates
    # with this shared secret instead of a bearer token. Blank disables the
    # route entirely rather than leaving it open.
    CRON_SECRET: str = os.getenv("CRON_SECRET", "")
    # Wall-clock budget for one cron tick's sending, so the request returns
    # before the scheduler's own HTTP timeout.
    CRON_MAX_SECONDS: int = int(os.getenv("CRON_MAX_SECONDS", "50"))

    # HTTP Basic auth gate for the whole dashboard and API.
    #
    # The app has no login screen of its own, and a public deployment URL is
    # therefore an open door to the address book and the sending path. When both
    # values are set every request must present them; when either is blank the
    # gate is disabled (local development and the test suite). The browser
    # prompts once per session, and ``/health``, the recipient-facing tracking
    # links and the secret-authenticated cron route are exempt.
    BASIC_AUTH_USER: str = os.getenv("BASIC_AUTH_USER", "")
    BASIC_AUTH_PASSWORD: str = os.getenv("BASIC_AUTH_PASSWORD", "")

    # Run ``init_db()`` and the workspace bootstrap at startup. Serverless
    # instances start constantly, and issuing schema checks on every cold start
    # is slow and racy, so a Vercel deployment sets this to false and runs
    # ``python scripts/init_db.py`` once against the real database instead.
    AUTO_INIT_DB: bool = os.getenv("AUTO_INIT_DB", "true").lower() == "true"

    # The live-log WebSocket needs a long-lived connection, which serverless
    # hosts cannot provide. When false the route is not registered and the UI
    # shows a static log instead of reconnecting forever.
    ENABLE_LIVE_LOGS: bool = (
        os.getenv("ENABLE_LIVE_LOGS", "true").lower() == "true"
    )

    # Upper bound on how long one request-driven queue drain may spend sending.
    # Pacing allows one message per minute, so this is deliberately small: the
    # remainder is picked up by the next cron tick rather than holding a
    # serverless invocation open until its timeout.
    SYNC_DRAIN_SECONDS: int = int(os.getenv("SYNC_DRAIN_SECONDS", "25"))

    # This app is a single-user tool: it runs one implicit workspace and serves
    # every request as that workspace, with no sign-in screen. The value is fixed
    # rather than read from the environment so a deploy cannot accidentally
    # require a login the UI no longer offers.
    SINGLE_USER_MODE: bool = True

    # Identity used for that implicit local tenant.
    LOCAL_USER_EMAIL: str = os.getenv("LOCAL_USER_EMAIL", "local@localhost")
    LOCAL_TENANT_NAME: str = os.getenv("LOCAL_TENANT_NAME", "Local")


# Global settings instance
settings = Settings()
