"""An auto-reply draft belongs to the contact's tenant so the scoped queue sends it."""
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agents
from app.db import Base, Contact, Draft, Event, Tenant


def test_auto_reply_uses_contact_tenant_and_sends_in_scoped_pass(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(agents, "SessionLocal", session_factory)
    monkeypatch.setattr(agents, "is_configured", lambda config: True)
    monkeypatch.setattr(agents, "send_email", lambda *args: None)

    db = session_factory()
    tenant = Tenant(name="Scoped Co", subdomain="scoped-co")
    db.add(tenant)
    db.commit()
    contact = Contact(
        tenant_id=tenant.id, email="lead@example.com", eligible_to_email=True
    )
    db.add(contact)
    db.commit()
    contact_id, tenant_id = contact.id, tenant.id
    db.close()

    responder = agents.AutoResponder(contact_id=contact_id)
    result = responder.send_response(
        {
            "to_email": "lead@example.com",
            "subject": "Re: Introduction",
            "body": "Thanks for your interest",
            "reply_event_id": 7,
        }
    )
    responder.log_interaction(7, result)
    responder.close()

    queued_db = session_factory()
    try:
        draft = queued_db.query(Draft).one()
        assert draft.tenant_id == tenant_id
        assert queued_db.query(Event).one().tenant_id == tenant_id
    finally:
        queued_db.close()

    queue_result = asyncio.run(agents.QueueManager().process_queue(tenant_id=tenant_id))

    sent_db = session_factory()
    try:
        assert queue_result["sent"] == 1
        assert sent_db.query(Draft).one().status == "sent"
    finally:
        sent_db.close()
        engine.dispose()
