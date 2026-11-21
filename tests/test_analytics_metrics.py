"""The Overview metrics: sends, replies, follow-ups and interested clients.

Every number is derived from tenant rows, so these tests seed one tenant's
drafts/events directly and then assert the ``/api/state`` analytics payload.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Event
from app.main import _build_analytics


def _factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False), engine


def _seed(db, tenant_id=1):
    contact = Contact(
        tenant_id=tenant_id, email=f"lead-{uuid.uuid4().hex[:6]}@example.com",
        name="Dana Reed", eligible_to_email=True,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Draft(tenant_id=tenant_id, contact_id=contact.id, subject="Intro",
                  body="Body", status="sent", sent_at=now,
                  variables={"campaign_type": "intro"}),
            # A follow-up that actually went out.
            Draft(tenant_id=tenant_id, contact_id=contact.id, subject="F/up 1",
                  body="Body", status="sent", sent_at=now,
                  variables={"followup_for": 1, "followup_stage": 3}),
            # A follow-up still waiting in the queue.
            Draft(tenant_id=tenant_id, contact_id=contact.id, subject="F/up 2",
                  body="Body", status="draft",
                  variables={"followup_for": 1, "followup_stage": 5}),
            # An intro draft that is not a follow-up.
            Draft(tenant_id=tenant_id, contact_id=contact.id, subject="Draft",
                  body="Body", status="draft", variables={"campaign_type": "intro"}),
        ]
    )
    db.add_all(
        [
            Event(tenant_id=tenant_id, contact_id=contact.id,
                  event_type="reply_received",
                  data={"classification": {"reply_type": "positive_response"}}),
            Event(tenant_id=tenant_id, contact_id=contact.id,
                  event_type="reply_received",
                  data={"classification": {"reply_type": "positive_response"}}),
            Event(tenant_id=tenant_id, contact_id=contact.id,
                  event_type="reply_received",
                  data={"classification": {"reply_type": "negative_response"}}),
        ]
    )
    db.commit()
    return contact


def test_followups_are_split_into_sent_and_queued():
    Session, engine = _factory()
    db = Session()
    try:
        _seed(db)
        analytics = _build_analytics(db, 1)

        assert analytics["followups_sent"] == 1
        assert analytics["followups_due"] == 1
        assert analytics["pending"] == 2
        assert analytics["sent"] == 2
    finally:
        db.close()
        engine.dispose()


def test_interested_counts_distinct_positive_contacts():
    Session, engine = _factory()
    db = Session()
    try:
        contact = _seed(db)
        analytics = _build_analytics(db, 1)

        # Two positive replies from the same contact are one interested client.
        assert analytics["interested"] == 1
        assert analytics["interested_contacts"] == [contact.id]
        assert analytics["reply_types"] == {
            "positive_response": 2,
            "negative_response": 1,
        }
        assert analytics["replied"] == 3
    finally:
        db.close()
        engine.dispose()


def test_analytics_do_not_leak_across_tenants():
    Session, engine = _factory()
    db = Session()
    try:
        _seed(db, tenant_id=1)
        _seed(db, tenant_id=2)
        analytics = _build_analytics(db, 1)

        assert analytics["interested"] == 1
        assert analytics["followups_sent"] == 1
        assert analytics["sent"] == 2
    finally:
        db.close()
        engine.dispose()
