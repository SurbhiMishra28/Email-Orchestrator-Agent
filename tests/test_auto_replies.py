"""Automatic replies are queued through the regular send-limit path."""
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agents
from app.db import Base, Contact, Draft, Event


def test_auto_reply_is_queued_then_sent_by_queue_manager(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(agents, "SessionLocal", session_factory)
    monkeypatch.setattr(agents, "is_configured", lambda config: True)
    monkeypatch.setattr(agents, "send_email", lambda *args: None)

    db = session_factory()
    contact = Contact(email="lead@example.com", eligible_to_email=True)
    db.add(contact)
    db.commit()
    contact_id = contact.id
    db.close()

    responder = agents.AutoResponder(contact_id=contact_id)
    result = responder.send_response(
        {
            "to_email": "lead@example.com",
            "subject": "Re: Introduction",
            "body": "Thanks for your interest",
            "reply_event_id": 41,
        }
    )
    responder.log_interaction(41, result)
    responder.close()

    queued_db = session_factory()
    draft = queued_db.query(Draft).one()
    assert result["success"]
    assert draft.status == "draft"
    assert draft.variables["message_kind"] == "auto_reply"
    assert queued_db.query(Event).filter_by(event_type="auto_reply_queued").count() == 1
    queued_db.close()

    queue_result = asyncio.run(agents.QueueManager().process_queue())

    sent_db = session_factory()
    try:
        assert queue_result["sent"] == 1
        assert sent_db.query(Draft).one().status == "sent"
        assert sent_db.query(Event).filter_by(event_type="auto_reply_sent").count() == 1
    finally:
        sent_db.close()
        engine.dispose()
