"""The default alias must actually be used as the From identity.

An alias that is stored and displayed but never used when sending is worse than
no alias at all: "Make default" would silently change nothing.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agents
from app.db import Base, EmailAlias, Settings


def _session(monkeypatch, aliases):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(Settings(tenant_id=1))
    for name, email, is_default, is_active in aliases:
        db.add(
            EmailAlias(
                tenant_id=1,
                name=name,
                email=email,
                is_default=is_default,
                is_active=is_active,
            )
        )
    db.commit()
    return factory, engine


def test_default_alias_is_returned(monkeypatch):
    factory, engine = _session(
        monkeypatch,
        [("Sales", "sales@acme.test", True, True), ("Other", "other@acme.test", False, True)],
    )
    db = factory()
    try:
        assert agents.default_alias(db, 1) == ("Sales", "sales@acme.test")
    finally:
        db.close()
        engine.dispose()


def test_inactive_alias_is_ignored(monkeypatch):
    factory, engine = _session(
        monkeypatch, [("Sales", "sales@acme.test", True, False)]
    )
    db = factory()
    try:
        assert agents.default_alias(db, 1) == ("", "")
    finally:
        db.close()
        engine.dispose()


def test_no_alias_returns_empty_strings(monkeypatch):
    factory, engine = _session(monkeypatch, [])
    db = factory()
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
    db.add(Settings(tenant_id=1))
    db.add(Settings(tenant_id=2))
    db.add(EmailAlias(tenant_id=2, name="Other", email="other@acme.test", is_default=True))
    db.commit()
    try:
        # Tenant 1 has no alias of its own; it must not borrow tenant 2's.
        assert agents.default_alias(db, 1) == ("", "")
        assert agents.default_alias(db, 2) == ("Other", "other@acme.test")
    finally:
        db.close()
        engine.dispose()