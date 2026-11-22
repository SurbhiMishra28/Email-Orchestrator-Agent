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


def _test_url(url: str) -> str:
    """Return ``url`` pointed at this run's throwaway test database."""
    if url.startswith("sqlite"):
        return f"sqlite:///./{_SQLITE_PATH}"
    base, _, _ = url.rpartition("/")
    return f"{base}/{_TEST_DB_NAME}"


TEST_DATABASE_URL = _test_url(_REAL_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# The suite deliberately mails reserved example.com addresses, so the
# "refuse placeholder recipients" guard must be off while it runs.
os.environ["BLOCK_PLACEHOLDER_RECIPIENTS"] = "false"

# .env points at the developer's real Gmail account, and a new tenant is
# provisioned with those credentials. Without this the suite would send real
# email (and collect real bounces) from that account.
os.environ["MAIL_SUPPRESS_SEND"] = "true"


def _ensure_test_database() -> None:
    """Create the throwaway database if the server does not have it yet."""
    if TEST_DATABASE_URL.startswith("sqlite"):
        return

    from sqlalchemy import create_engine, text

    server_url = TEST_DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS {_TEST_DB_NAME} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        engine.dispose()


from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

_ensure_test_database()


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

    server_url = TEST_DATABASE_URL.rsplit("/", 1)[0]
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    try:
        # App connections can outlive the fixture for a moment, and MariaDB
        # refuses to drop a schema that still has sessions attached.
        for attempt in range(5):
            try:
                with admin.connect() as connection:
                    connection.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME}"))
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1)
    finally:
        admin.dispose()
