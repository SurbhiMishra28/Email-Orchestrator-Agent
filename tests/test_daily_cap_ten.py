"""The daily cap is ten, with no warm-up ramp and a per-domain cap that allows it.

Sending ten messages to one provider in a day is the whole point of the new
configuration, so the domain cap must not be the thing that blocks it.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Settings
from app.services import limits
from app.services.limits import POST_WARMUP_CAP, check_send_allowed, warmup_cap


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