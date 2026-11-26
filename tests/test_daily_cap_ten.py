"""The default daily cap is ten, with no warm-up ramp and a per-domain cap that
allows it.

Sending ten messages to one provider in a day is the whole point of the default
configuration, so the domain cap must not be the thing that blocks it. A
deployment may raise the ceiling with ``DAILY_CAP``; the default stays ten.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Settings
from app.services import limits
from app.services.limits import POST_WARMUP_CAP, check_send_allowed, warmup_cap


@pytest.fixture(autouse=True)
def _default_ceiling(monkeypatch):
    """Pin the unset-``DAILY_CAP`` behaviour regardless of the developer .env."""
    monkeypatch.setattr(limits, "DAILY_CAP", POST_WARMUP_CAP)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Contact(email="lead@example.com", eligible_to_email=True, tenant_id=1))
    session.add(Settings(tenant_id=1, daily_cap=10, domain_cap=10))
    session.commit()
    return session, engine


def _sent(db, contact_id, when, subject="Intro"):
    db.add(Draft(contact_id=contact_id, subject=subject, body="b",
                 status="sent", sent_at=when, tenant_id=1))
    db.commit()


def test_cap_is_ten():
    assert POST_WARMUP_CAP == 10


def test_no_warmup_ramp():
    db, engine = _db()
    try:
        now = datetime.now(timezone.utc)
        assert warmup_cap(db, 1, now) == 10
        # Ten sends already today, the eleventh is refused.
        for i in range(10):
            _sent(db, 1, now - timedelta(seconds=120 * (i + 1)), f"M{i}")
        allowed, reason = check_send_allowed(db, db.query(Contact).first(), now)
        assert not allowed
        assert "cap" in reason.lower()
    finally:
        db.close()
        engine.dispose()


def test_ten_in_one_domain_are_allowed_before_the_cap():
    """The domain cap must not block the ten the daily cap permits."""
    db, engine = _db()
    try:
        now = datetime.now(timezone.utc)
        for i in range(9):
            _sent(db, 1, now - timedelta(seconds=120 * (i + 1)), f"M{i}")
        allowed, reason = check_send_allowed(db, db.query(Contact).first(), now)
        assert allowed, reason
    finally:
        db.close()
        engine.dispose()


def test_daily_cap_env_raises_the_ceiling(monkeypatch):
    """``DAILY_CAP`` is the deployment override; 50 sends then 51 is refused."""
    monkeypatch.setattr(limits, "DAILY_CAP", 50)
    db, engine = _db()
    try:
        db.query(Settings).update({"daily_cap": 50, "domain_cap": 50})
        db.commit()
        now = datetime.now(timezone.utc)
        assert warmup_cap(db, 1, now) == 50
        for i in range(50):
            _sent(db, 1, now - timedelta(seconds=120 * (i + 1)), f"M{i}")
        allowed, reason = check_send_allowed(db, db.query(Contact).first(), now)
        assert not allowed
        assert "50/50" in reason
    finally:
        db.close()
        engine.dispose()


def test_invalid_daily_cap_env_falls_back_to_default(monkeypatch):
    """A zero or non-numeric ``DAILY_CAP`` must not disable the cap."""
    for raw in ("0", "-5", "fifty"):
        monkeypatch.setenv("DAILY_CAP", raw)
        assert limits._env_int("DAILY_CAP", POST_WARMUP_CAP) == POST_WARMUP_CAP
