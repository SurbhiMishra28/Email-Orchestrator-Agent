"""Startup and health behaviour when the configured database is unreachable.

A wrong ``DATABASE_URL`` used to kill the process during startup, which a
platform reports as a crashed deploy with no diagnostics. These tests pin the
contract: the app stays up, ``/health`` reports 503, and background jobs are
skipped instead of failing repeatedly.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def _raise_operational_error(*args, **kwargs):
    raise OperationalError("SELECT 1", {}, Exception("Can't connect to MySQL server"))


def test_health_reports_503_when_database_is_down(monkeypatch):
    from app import main as main_module

    class BrokenSession:
        def execute(self, *args, **kwargs):
            _raise_operational_error()

        def close(self):
            pass

    monkeypatch.setattr(main_module, "SessionLocal", lambda: BrokenSession())

    with TestClient(main_module.app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["healthy"] is False


def test_health_stays_200_when_database_is_up():
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"]["database"]["healthy"] is True


def test_lifespan_survives_database_outage(monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(main_module, "init_db", _raise_operational_error)
    monkeypatch.setattr(
        main_module,
        "_bootstrap_database",
        lambda: pytest.fail("provisioning should be skipped without a schema"),
    )

    async def run() -> None:
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(run())

    assert not main_module.scheduler.running


def test_database_url_description_hides_password():
    from app.db import _describe_database_url

    described = _describe_database_url(
        "mysql+pymysql://root:sup3rsecret@db.internal:3306/email_orchestrator"
    )

    assert "sup3rsecret" not in described
    assert described == "mysql+pymysql://root:***@db.internal:3306/email_orchestrator"


def test_platform_public_url_reads_render_origin(monkeypatch):
    from app import config

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://mailmatrix.onrender.com/")
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)

    assert config._platform_public_url() == "https://mailmatrix.onrender.com"


def test_platform_public_url_adds_scheme_for_railway(monkeypatch):
    from app import config

    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "email-orchestrator.up.railway.app")
    monkeypatch.delenv("FLY_APP_NAME", raising=False)

    assert (
        config._platform_public_url()
        == "https://email-orchestrator.up.railway.app"
    )


def test_platform_public_url_empty_without_a_platform(monkeypatch):
    from app import config

    for name in ("RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN", "FLY_APP_NAME"):
        monkeypatch.delenv(name, raising=False)

    assert config._platform_public_url() == ""


def _import_db_with(url: str, extra_env=None) -> str:
    """Import app.db in a fresh interpreter and return its resolved URL.

    The engine is built at import time, so the scheme rewrite and directory
    preparation can only be observed in a subprocess.
    """
    import os
    import subprocess
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "DATABASE_URL": url, **(extra_env or {})}
    env.pop("RENDER", None)
    env.pop("RAILWAY_ENVIRONMENT", None)
    env.pop("FLY_APP_NAME", None)
    completed = subprocess.run(
        [sys.executable, "-c", "from app.db import DATABASE_URL; print(DATABASE_URL)"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@pytest.mark.parametrize(
    "given,expected",
    [
        ("mysql://u:p@host:3306/db", "mysql+pymysql://u:p@host:3306/db"),
        ("mariadb://u:p@host:3306/db", "mysql+pymysql://u:p@host:3306/db"),
        ("mysql+pymysql://u:p@host:3306/db", "mysql+pymysql://u:p@host:3306/db"),
    ],
)
def test_provider_mysql_urls_are_rewritten_for_pymysql(given, expected):
    assert _import_db_with(given) == expected


def test_sqlite_parent_directory_is_created(tmp_path):
    target = tmp_path / "var" / "data" / "email_orchestrator.db"

    resolved = _import_db_with(f"sqlite:///{target.as_posix()}")

    assert resolved == f"sqlite:///{target.as_posix()}"
    assert target.parent.is_dir()
