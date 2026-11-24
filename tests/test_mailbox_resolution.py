"""A blank mailbox row must not make the app claim SMTP/IMAP is unconfigured.

The dashboard used to read only the stored per-tenant rows, so a fresh install
(or a row reset in Settings) reported "SMTP is not configured" even though the
deployment's ``.env`` held working credentials. These tests pin the resolver that
now answers both questions, including the security boundary: only the local
single-user tenant may fall back to the environment.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, IMAPConfig, SMTPConfig, Tenant
from app.services import inbox, mailer


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def environment(monkeypatch):
    """A deployment .env with both mailboxes filled in."""
    defaults = {
        "DEFAULT_SMTP_HOST": "smtp.gmail.com",
        "DEFAULT_SMTP_PORT": 587,
        "DEFAULT_SMTP_USER": "operator@gmail.com",
        "DEFAULT_SMTP_PASSWORD": "operator-app-password",
        "DEFAULT_SMTP_SENDER": "operator@gmail.com",
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_PORT": 993,
        "IMAP_USER": "operator@gmail.com",
        "IMAP_PASSWORD": "operator-app-password",
    }
    for name, value in defaults.items():
        monkeypatch.setattr(mailer.app_settings, name, value, raising=False)
        monkeypatch.setattr(inbox.settings, name, value, raising=False)

@pytest.fixture
def single_user(monkeypatch):
    # ``mailer.app_settings`` and ``inbox.settings`` are the same object.
    monkeypatch.setattr(mailer.app_settings, "SINGLE_USER_MODE", True, raising=False)


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(mailer.app_settings, "SINGLE_USER_MODE", False, raising=False)


def _tenants(db, *ids):
    for tenant_id in ids:
        db.add(Tenant(id=tenant_id, name=f"Tenant {tenant_id}"))
    db.commit()


def test_blank_smtp_row_resolves_to_the_local_environment(db, environment, single_user):
    _tenants(db, 1)
    db.add(SMTPConfig(tenant_id=1))
    db.commit()

    view = mailer.resolve_smtp_config(db, 1)

    assert view.host == "smtp.gmail.com"
    assert view.authentication_configured is True
    assert view.configured is True
    assert view.source == "environment"


def test_missing_smtp_row_resolves_to_the_local_environment(db, environment, single_user):
    _tenants(db, 1)

    view = mailer.resolve_smtp_config(db, 1)

    assert view.configured is True
    assert view.sender == "operator@gmail.com"


def test_a_saved_row_wins_over_the_environment(db, environment, single_user):
    _tenants(db, 1)
    db.add(
        SMTPConfig(
            tenant_id=1,
            host="smtp.mailprovider.test",
            port=465,
            user="owner@mailprovider.test",
            password="own-password",
            sender="owner@mailprovider.test",
            configured=True,
            authentication_configured=True,
        )
    )
    db.commit()

    view = mailer.resolve_smtp_config(db, 1)

    assert view.host == "smtp.mailprovider.test"
    assert view.source == "database"


def test_a_partial_row_is_completed_from_the_environment(db, environment, single_user):
    _tenants(db, 1)
    db.add(SMTPConfig(tenant_id=1, host="smtp.gmail.com", user="operator@gmail.com"))
    db.commit()

    view = mailer.resolve_smtp_config(db, 1)

    assert view.password == "operator-app-password"
    assert view.sender == "operator@gmail.com"


def test_a_registered_tenant_never_sees_the_operator_mailbox(db, environment, single_user):
    """The security boundary: only the lowest tenant id is the local owner."""
    _tenants(db, 1, 60)
    db.add(SMTPConfig(tenant_id=60))
    db.commit()

    view = mailer.resolve_smtp_config(db, 60)

    assert view.host == ""
    assert view.configured is False


def test_a_hosted_deployment_disables_the_fallback_entirely(db, environment, hosted):
    _tenants(db, 1)
    db.add(SMTPConfig(tenant_id=1))
    db.commit()

    view = mailer.resolve_smtp_config(db, 1)

    assert view.configured is False


def test_blank_imap_row_resolves_to_the_local_environment(db, environment, single_user):
    _tenants(db, 1)
    db.add(IMAPConfig(tenant_id=1))
    db.commit()

    view = inbox.resolve_imap_config(db, 1)

    assert view.host == "imap.gmail.com"
    assert view.configured is True
    assert view.source == "environment"


def test_imap_is_not_shared_with_a_registered_tenant(db, environment, single_user):
    _tenants(db, 1, 60)

    assert inbox.resolve_imap_config(db, 60).configured is False


def test_gmail_api_resolves_for_the_local_workspace_only(db, single_user, monkeypatch):
    from app.config import settings

    _tenants(db, 1, 60)
    monkeypatch.setattr(settings, "MAIL_TRANSPORT", "gmail_api")
    monkeypatch.setattr(settings, "GMAIL_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GMAIL_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "GMAIL_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(settings, "GMAIL_USER_EMAIL", "operator@gmail.com")

    smtp = mailer.resolve_smtp_config(db, 1)
    inbox_view = inbox.resolve_imap_config(db, 1)

    assert smtp.configured is True
    assert smtp.sender == "operator@gmail.com"
    assert smtp.source == "environment"
    assert inbox_view.configured is True
    assert inbox_view.api_mode is True

    assert mailer.is_configured(mailer.resolve_smtp_config(db, 60)) is False
    assert inbox.resolve_imap_config(db, 60).configured is False
