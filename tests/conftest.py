"""Test fixtures that keep the suite off the developer's real data.

The app reads ``DATABASE_URL`` at import time, so this module installs a
throwaway copy of the configured database *before* ``app`` is imported. The
copy is created, migrated and dropped by the suite, which means tests can use
the same engine as production (MariaDB) without touching real rows.
"""
import os
import time
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

_REAL_URL = os.getenv("DATABASE_URL") or "sqlite:///./test_email_orchestrator.db"

# A unique schema per run keeps two concurrent pytest processes from dropping
# each other's tables mid-test.
_RUN_ID = os.getenv("PYTEST_RUN_ID") or uuid.uuid4().hex[:8]
_TEST_DB_NAME = f"email_orchestrator_test_{_RUN_ID}"
_SQLITE_PATH = f"test_email_orchestrator_{_RUN_ID}.db"


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


def _admin_url() -> str:
    """The server-level URL used to create/drop the throwaway database.

    For Postgres the unpooled endpoint is used when the platform supplies one:
    ``CREATE DATABASE`` cannot run through PgBouncer's transaction pooler.
    """
    if _is_postgres(_REAL_URL):
        return os.getenv("DATABASE_URL_UNPOOLED") or _REAL_URL
    return _REAL_URL


def _test_url(url: str) -> str:
    """Return ``url`` pointed at this run's throwaway test database.

    Postgres URLs carry libpq options in the query string (``sslmode=require``),
    so the swap has to preserve them -- dropping them downgrades the connection
    to plaintext and the server refuses it.
    """
    if url.startswith("sqlite"):
        return f"sqlite:///./{_SQLITE_PATH}"

    scheme, sep, rest = url.partition("://")
    head, qsep, query = rest.partition("?")
    base, _, _ = head.rpartition("/")
    swapped = f"{scheme}{sep}{base}/{_TEST_DB_NAME}"
    if qsep:
        swapped = f"{swapped}?{query}"
    return swapped


# Build the test URL from the *direct* endpoint, not the pooled one. PgBouncer
# in transaction mode cannot serve a freshly created database reliably (it
# terminates the connection mid-introspection), and the suite is a single
# long-lived process, so it does not need pooling.
TEST_DATABASE_URL = _test_url(_admin_url())
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# The suite deliberately mails reserved example.com addresses, so the
# "refuse placeholder recipients" guard must be off while it runs.
os.environ["BLOCK_PLACEHOLDER_RECIPIENTS"] = "false"

# .env points at the developer's real Gmail account, and a new tenant is
# provisioned with those credentials. Without this the suite would send real
# email (and collect real bounces) from that account.
os.environ["MAIL_SUPPRESS_SEND"] = "true"

# The developer's .env also carries a RESEND_API_KEY, and for a long time a
# present key silently overrode SMTP. Tests that opt out of dry-run mode build a
# real message, so with the key in play they would call the Resend API and fail
# on a network/DNS error instead of exercising the mailer. Pin the transport.
os.environ["MAIL_TRANSPORT"] = "smtp"

# The local .env mirrors a serverless deployment, where AUTO_INIT_DB=false
# because schema creation runs once via scripts/init_db.py. The suite creates a
# throwaway database per session and needs the schema built in it, so it must
# not inherit that production setting.
os.environ["AUTO_INIT_DB"] = "true"

# DATABASE_URL_UNPOOLED is the migration endpoint for the *deployed* database.
# Leaving it set would send this session's DDL to that database instead of the
# throwaway one, so the suite has a single endpoint for everything.
os.environ["DATABASE_URL_UNPOOLED"] = ""

# The local .env mirrors a serverless deployment, which disables the in-process
# scheduler, the background send worker and the live-log socket. The suite
# asserts the behaviour of all three, so it pins them on rather than inheriting
# whatever the deployed configuration happens to be.
os.environ["ENABLE_BACKGROUND_JOBS"] = "true"
os.environ["ENABLE_LIVE_LOGS"] = "true"

# The developer's .env may raise the daily ceiling (DAILY_CAP) for a real batch.
# Tests assert the code's own default, so the deployment override is cleared
# here; a test that wants a different ceiling monkeypatches
# ``app.services.limits.DAILY_CAP``.
os.environ["DAILY_CAP"] = ""


def _ensure_test_database() -> None:
    """Create the throwaway database if the server does not have it yet.

    DDL cannot run inside a transaction on Postgres, so the admin connection is
    opened with AUTOCOMMIT and ``CREATE DATABASE`` is issued bare. A concurrent
    run that already created it is not an error.
    """
    if TEST_DATABASE_URL.startswith("sqlite"):
        return

    from sqlalchemy import create_engine, text

    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with admin.connect() as connection:
            if _is_postgres(TEST_DATABASE_URL):
                try:
                    connection.execute(text(f'CREATE DATABASE "{_TEST_DB_NAME}"'))
                except Exception as exc:
                    if "already exists" not in str(exc).lower():
                        raise
            else:
                connection.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS {_TEST_DB_NAME} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
    finally:
        admin.dispose()


from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

_ensure_test_database()


@pytest.fixture(scope="session", autouse=True)
def _no_background_scheduler():
    """Stop APScheduler from firing in the middle of a test.

    The suite runs for minutes, and the lifespan starts an inbox poll and an
    autopilot timer whenever ``ENABLE_BACKGROUND_JOBS`` is true. A timer that
    drains the queue while another test is capturing sends shows up as a
    surprise recipient in a test that never asked for one, which is very hard to
    attribute from the assertion alone.

    The worker handoff itself is still tested with the flag on; only the timers
    are suppressed, and every path the suite covers is driven explicitly.
    """
    from app import main as app_main

    app_main.scheduler.start = lambda *args, **kwargs: None
    app_main.scheduler.shutdown = lambda *args, **kwargs: None
    yield


@pytest.fixture(scope="session")
def client():
    """Authenticated TestClient bound to a freshly registered tenant."""
    with TestClient(app) as test_client:
        import uuid

        suffix = uuid.uuid4().hex[:10]
        response = test_client.post(
            "/api/auth/register",
            json={
                "email": f"fixture-{suffix}@example.com",
                "password": "test-password-123",
                "name": "Fixture User",
                "tenant_name": f"Fixture Tenant {suffix}",
            },
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client


def pytest_sessionfinish(session, exitstatus):
    """Drop the throwaway database so the next run starts clean."""
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    if TEST_DATABASE_URL.startswith("sqlite"):
        for path in (_SQLITE_PATH, f"{_SQLITE_PATH}-journal"):
            try:
                os.remove(path)
            except OSError:
                pass
        return

    from sqlalchemy import create_engine, text

    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        # App connections can outlive the fixture for a moment. Postgres 13+
        # can terminate them with WITH (FORCE); MySQL needs the retry loop.
        for attempt in range(5):
            try:
                with admin.connect() as connection:
                    if _is_postgres(TEST_DATABASE_URL):
                        connection.execute(
                            text(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
                        )
                    else:
                        connection.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME}"))
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1)
    finally:
        admin.dispose()
