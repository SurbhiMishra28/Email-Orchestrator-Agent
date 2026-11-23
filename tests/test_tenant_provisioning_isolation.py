"""A newly registered tenant must never inherit the operator's mailbox.

The deployment's environment holds the operator's SMTP password so the local
single-user tool can send. Registration is open to anyone, so copying that value
into every new tenant let any visitor send mail as the operator. These tests pin
the boundary against a real (in-memory) database so they exercise the same code
path registration uses.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, SMTPConfig, Settings
from app.services import provisioning


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
def operator_environment(monkeypatch):
    """Fake a deployment .env that has real credentials and unattended sending."""
    defaults = {
        "DEFAULT_SMTP_HOST": "smtp.gmail.com",
        "DEFAULT_SMTP_USER": "operator@gmail.com",
        "DEFAULT_SMTP_PASSWORD": "operator-app-password",
        "DEFAULT_SMTP_SENDER": "operator@gmail.com",
        "DEFAULT_AUTOPILOT": True,
        "DEFAULT_AUTO_APPROVE": True,
    }
    for name, value in defaults.items():
        monkeypatch.setattr(provisioning.app_settings, name, value, raising=False)


def test_registered_tenant_does_not_receive_operator_credentials(
    db, operator_environment
):
    provisioning.provision_tenant_defaults(db, tenant_id=42, inherit_environment=False)

    smtp = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == 42).one()
    settings_row = db.query(Settings).filter(Settings.tenant_id == 42).one()

    assert smtp.host in (None, "")
    assert smtp.user in (None, "")
    assert smtp.password in (None, "")
    assert smtp.sender in (None, "")
    assert smtp.configured is False
    assert settings_row.AUTOPILOT is False
    assert settings_row.AUTO_APPROVE is False


def test_local_single_user_tenant_still_inherits_the_mailbox(db, operator_environment):
    """The local tool has one implicit tenant, which is the mailbox owner."""
    provisioning.provision_tenant_defaults(db, tenant_id=1, inherit_environment=True)

    smtp = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == 1).one()

    assert smtp.host == "smtp.gmail.com"
    assert smtp.user == "operator@gmail.com"
    assert smtp.password == "operator-app-password"
    assert smtp.configured is True


def test_inheritance_defaults_to_on(db, operator_environment):
    """A new tenant in this single-workspace build inherits the mailbox."""
    provisioning.provision_tenant_defaults(db, tenant_id=7)

    smtp = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == 7).one()
    assert smtp.password == "operator-app-password"


def test_starter_templates_are_still_created_for_a_new_tenant(
    db, operator_environment
):
    """Isolation must not leave a new workspace without usable templates."""
    provisioning.provision_tenant_defaults(db, tenant_id=9, inherit_environment=False)

    from app.db import Template

    names = {row.name for row in db.query(Template).filter(Template.tenant_id == 9)}
    assert names == {"Intro Email", "Follow-up"}
