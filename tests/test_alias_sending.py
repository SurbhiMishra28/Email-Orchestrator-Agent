"""A campaign or draft can pin the sender alias it is sent from.

Without this the alias list in Settings is decorative: every send would use the
tenant default and "Make default" would appear to do nothing.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agents
from app.db import Base, Draft, EmailAlias, Settings, Tenant


def _session(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(Tenant(id=1, name="T"))
    db.add(Settings(tenant_id=1))
    db.add(EmailAlias(tenant_id=1, name="Sales", email="sales@acme.test", is_default=True, is_active=True))
    db.add(EmailAlias(tenant_id=1, name="Support", email="support@acme.test", is_default=False, is_active=True))
    db.commit()
    return factory, engine


def test_default_alias_used_when_draft_has_none(monkeypatch):
    factory, engine = _session(monkeypatch)
    db = factory()
    try:
        assert agents.default_alias(db, 1) == ("Sales", "sales@acme.test")
    finally:
        db.close()
        engine.dispose()


def test_draft_alias_overrides_the_default(monkeypatch):
    factory, engine = _session(monkeypatch)
    db = factory()
    try:
        draft = Draft(
            contact_id=1,
            subject="Hi",
            body="Body",
            status="draft",
            tenant_id=1,
            variables={"from_email": "support@acme.test", "from_name": "Support"},
        )
        assert agents.default_alias(db, 1, draft) == ("Support", "support@acme.test")
    finally:
        db.close()
        engine.dispose()


def test_inactive_alias_is_not_used(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(Tenant(id=1, name="T"))
    db.add(Settings(tenant_id=1))
    db.add(EmailAlias(tenant_id=1, name="Sales", email="sales@acme.test", is_default=True, is_active=False))
    db.commit()
    try:
        assert agents.default_alias(db, 1) == ("", "")
    finally:
        db.close()
        engine.dispose()


def test_alias_is_scoped_to_the_tenant(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(Tenant(id=1, name="A"))
    db.add(Tenant(id=2, name="B"))
    db.add(Settings(tenant_id=1))
    db.add(Settings(tenant_id=2))
    db.add(EmailAlias(tenant_id=2, name="Other", email="other@acme.test", is_default=True, is_active=True))
    db.commit()
    try:
        assert agents.default_alias(db, 1) == ("", "")
    finally:
        db.close()
        engine.dispose()