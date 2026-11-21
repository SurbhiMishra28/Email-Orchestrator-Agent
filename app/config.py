"""Application configuration with environment variable support."""
import os
from typing import Optional

from dotenv import load_dotenv

# Load the project-level .env before any setting below reads the environment.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


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

    # Follow-up drafting (never sends on its own)
    FOLLOWUPS_ENABLED: bool = os.getenv("FOLLOWUPS_ENABLED", "true").lower() == "true"

    # Absolute origin used to build open-pixel and click-tracking URLs. It must
    # be reachable by recipients, so a public deployment sets it explicitly;
    # the default keeps local development working.
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

    # How many queue passes one process may run at once. Sending is still
    # serialized per tenant by the pacing rule in ``services/limits.py``; this
    # bounds how much work a burst of async submissions can start.
    SEND_CONCURRENCY: int = int(os.getenv("SEND_CONCURRENCY", "2"))
    
    # CORS - loopback origins by default; wildcard + credentials is invalid.
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,"
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    
    # NVIDIA API
    NVIDIA_API_KEY: Optional[str] = os.getenv("NVIDIA_API_KEY")
    NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "nvidia/nllama-3.1-nemotron-70b-instruct")
    
    # Frontend
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:8000")

    # JWT Settings for SaaS authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    # When true the app runs as a single-user local tool: one implicit tenant is
    # provisioned at startup and requests do not need a bearer token. Set to
    # false for the multi-tenant SaaS deployment.
    SINGLE_USER_MODE: bool = os.getenv("SINGLE_USER_MODE", "true").lower() == "true"
    # Identity used for that implicit local tenant.
    LOCAL_USER_EMAIL: str = os.getenv("LOCAL_USER_EMAIL", "local@localhost")
    LOCAL_TENANT_NAME: str = os.getenv("LOCAL_TENANT_NAME", "Local")


# Global settings instance
settings = Settings()