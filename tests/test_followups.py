"""Follow-up generation tests against an isolated SQLite database."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Event
from app.services import followups


@pytest.fixture
def followup_db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(followups, "SessionLocal", session_factory)

    async def expand_template(template, contact):
        return {"subject": "Follow-up", "body": "Checking in"}

    import app.agents

    monkeypatch.setattr(app.agents, "expand_template_with_ai", expand_template)
    try:
        yield session_factory
    finally:
        engine.dispose()


def _sent_intro(db, contact, sent_at):
    draft = Draft(
        contact_id=contact.id,
        subject="Introduction",
        body="Hello",
        status="sent",
        sent_at=sent_at,
        variables={"campaign_type": "intro"},
    )
    db.add(draft)
    db.commit()
    return draft


def test_due_followup_is_not_created_after_contact_replies(followup_db):
    db = followup_db()
    now = datetime.now(timezone.utc)
    contact = Contact(email="lead@example.com", eligible_to_email=True)
    db.add(contact)
    db.commit()
    original = _sent_intro(db, contact, now - timedelta(days=4))
    db.add(
        Event(
            contact_id=contact.id,
            event_type="reply_received",
            data={"subject": "Re: Introduction"},
            timestamp=now - timedelta(days=1),
        )
    )
    db.commit()
    db.close()

    result = asyncio.run(followups.generate_followups(now))

    assert result["created"] == 0
    assert result["skipped"] == 1
    verify_db = followup_db()
    try:
        assert verify_db.query(Draft).filter(Draft.contact_id == contact.id).count() == 1
    finally:
        verify_db.close()


def test_due_followup_is_created_for_eligible_contact_without_reply(followup_db):
    db = followup_db()
    now = datetime.now(timezone.utc)
    contact = Contact(email="lead@example.com", eligible_to_email=True)
    db.add(contact)
    db.commit()
    _sent_intro(db, contact, now - timedelta(days=4))
    db.close()

    result = asyncio.run(followups.generate_followups(now))

    assert result["created"] == 1
    verify_db = followup_db()
    try:
        drafts = verify_db.query(Draft).filter(Draft.contact_id == contact.id).all()
        assert len(drafts) == 2
        assert drafts[-1].variables["followup_stage"] == 3
    finally:
        verify_db.close()


def test_auto_reply_is_not_used_as_a_followup_source(followup_db):
    db = followup_db()
    now = datetime.now(timezone.utc)
    contact = Contact(email="lead@example.com", eligible_to_email=True)
    db.add(contact)
    db.commit()
    db.add(
        Draft(
            contact_id=contact.id,
            subject="Re: Introduction",
            body="Thanks for your interest",
            status="sent",
            sent_at=now - timedelta(days=4),
            variables={"message_kind": "auto_reply"},
        )
    )
    db.commit()
    db.close()

    result = asyncio.run(followups.generate_followups(now))

    assert result["created"] == 0
    verify_db = followup_db()
    try:
        assert verify_db.query(Draft).filter(Draft.contact_id == contact.id).count() == 1
    finally:
        verify_db.close()


def test_day_five_followup_waits_for_day_three_send(followup_db):
    db = followup_db()
    now = datetime.now(timezone.utc)
    contact = Contact(email="lead@example.com", eligible_to_email=True)
    db.add(contact)
    db.commit()
    original = _sent_intro(db, contact, now - timedelta(days=6))
    day_three = Draft(
        contact_id=contact.id,
        subject="Day 3",
        body="Checking in",
        status="draft",
        variables={"followup_for": original.id, "followup_stage": 3},
    )
    db.add(day_three)
    db.commit()
    db.close()

    result = asyncio.run(followups.generate_followups(now))
    assert result["created"] == 0

    db = followup_db()
    day_three = next(
        draft
        for draft in db.query(Draft).filter(Draft.contact_id == contact.id)
        if (draft.variables or {}).get("followup_stage") == 3
    )
    day_three.status = "sent"
    day_three.sent_at = now - timedelta(days=3)
    db.commit()
    db.close()

    result = asyncio.run(followups.generate_followups(now))
    assert result["created"] == 1
    verify_db = followup_db()
    try:
        stages = {
            draft.variables.get("followup_stage")
            for draft in verify_db.query(Draft).filter(Draft.contact_id == contact.id)
            if draft.variables.get("followup_for")
        }
        assert stages == {3, 5}
    finally:
        verify_db.close()
