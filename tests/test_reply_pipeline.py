"""The reply pipeline answers replies by itself, with no human review gate."""
import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.agents
from app import main as app_main
from app.db import Base, Contact, Draft, InboxMessage


@pytest.fixture
def reply_db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(app_main, "SessionLocal", session_factory)
    monkeypatch.setattr(app.agents, "SessionLocal", session_factory)
    try:
        yield session_factory
    finally:
        engine.dispose()


def _message(session_factory, uid, body):
    db = session_factory()
    db.add(Contact(email="lead@example.com", name="Lee Anne", eligible_to_email=True))
    db.add(
        InboxMessage(
            uid=uid,
            sender="Lee Anne <lead@example.com>",
            subject="Re: A quick introduction",
            snippet=body,
            received_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.close()


def test_positive_reply_is_answered_without_review(reply_db):
    _message(reply_db, "1001", "Yes, I'm interested and would like to talk.")

    queued = asyncio.run(app_main._process_incoming_replies())

    assert queued == 1
    db = reply_db()
    try:
        draft = db.query(Draft).one()
        assert draft.variables["message_kind"] == "auto_reply"
        assert draft.status == "draft"
        assert draft.subject.startswith("Re:")
    finally:
        db.close()


def test_spam_reply_is_recorded_but_not_answered(reply_db):
    _message(reply_db, "1002", "CONGRATULATIONS winner, click here to claim the lottery prize")

    queued = asyncio.run(app_main._process_incoming_replies())

    assert queued == 0
    db = reply_db()
    try:
        assert db.query(Draft).count() == 0
        assert db.query(InboxMessage).one().processed is True
    finally:
        db.close()
