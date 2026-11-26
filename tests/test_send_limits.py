"""Unit tests for send limits and pacing, against an isolated SQLite database."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Settings
from app.services.limits import DEFAULT_PACING_SECONDS, check_send_allowed


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Contact(email="lead@example.com", eligible_to_email=True))
    session.add(Settings(daily_cap=50, domain_cap=3))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _sent(db, contact_id, when, subject="Intro"):
    db.add(
        Draft(
            contact_id=contact_id,
            subject=subject,
            body="body",
            status="sent",
            sent_at=when,
        )
    )
    db.commit()


def test_first_send_is_allowed(db):
    contact = db.query(Contact).first()
    allowed, reason = check_send_allowed(db, contact)
    assert allowed, reason


def test_pacing_blocks_a_second_send_within_a_minute(db):
    contact = db.query(Contact).first()
    now = datetime.now(timezone.utc)
    _sent(db, contact.id, now - timedelta(seconds=5))

    allowed, reason = check_send_allowed(db, contact, now)

    assert not allowed
    assert reason.startswith("Pacing")
    assert DEFAULT_PACING_SECONDS == 60


def test_daily_cap_blocks_after_warmup_limit(db):
    contact = db.query(Contact).first()
    now = datetime.now(timezone.utc)
    for index in range(5):
        _sent(
            db,
            contact.id,
            now - timedelta(seconds=120 * (index + 1)),
            subject=f"Message {index}",
        )

    allowed, reason = check_send_allowed(db, contact, now)

    assert not allowed
    assert "cap" in reason.lower()


def test_domain_cap_blocks_repeat_recipients(db):
    contact = db.query(Contact).first()
    now = datetime.now(timezone.utc)
    # Keep the daily count in range and the pacing window open, but use up the
    # three allowed sends for example.com.
    for index in range(3):
        _sent(
            db,
            contact.id,
            now - timedelta(seconds=120 * (index + 1)),
            subject=f"Message {index}",
        )

    allowed, reason = check_send_allowed(db, contact, now)

    assert not allowed
    assert "Domain cap" in reason
