"""Tracking API output tests against an isolated SQLite database."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Event
from app.routers import tracking


def test_tracking_includes_reply_outcome_and_followup_history(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(tracking, "SessionLocal", session_factory)

    now = datetime.now(timezone.utc)
    db = session_factory()
    contact = Contact(
        email="lead@example.com",
        name="Lead",
        eligible_to_email=True,
        tenant_id=1,
    )
    db.add(contact)
    db.commit()
    original = Draft(
        contact_id=contact.id,
        subject="Introduction",
        body="Hello",
        status="sent",
        variables={"campaign_type": "intro"},
        sent_at=now - timedelta(days=4),
        tenant_id=1,
    )
    db.add(original)
    db.commit()
    followup = Draft(
        contact_id=contact.id,
        subject="Following up",
        body="Checking in",
        status="sent",
        variables={"followup_for": original.id, "followup_stage": 3},
        sent_at=now - timedelta(days=1),
        tenant_id=1,
    )
    reply = Event(
        contact_id=contact.id,
        event_type="reply_received",
        tenant_id=1,
        data={
            "sender_email": contact.email,
            "subject": "Re: Introduction",
            "classification": {
                "reply_type": "positive_response",
                "sentiment": "positive",
            },
        },
        timestamp=now,
    )
    db.add_all([followup, reply])
    db.commit()
    db.add(
        Event(
            contact_id=contact.id,
            event_type="auto_reply_sent",
            tenant_id=1,
            data={"reply_event_id": reply.id, "message": "Sent"},
            timestamp=now,
        )
    )
    db.commit()
    db.close()

    try:
        result = tracking.get_tracking(tenant_id=1)

        assert result["emails"][0]["interest"] == "Interested"
        assert result["emails"][0]["next_action"] == "Stopped after reply"
        assert result["emails"][0]["followups_sent"] == 1
        assert result["followups"][0]["stage"] == 3
        assert result["replies"][0]["auto_reply_status"] == "sent"
        assert result["reply_count"] == 1
        assert result["auto_replies_sent"] == 1
    finally:
        engine.dispose()
