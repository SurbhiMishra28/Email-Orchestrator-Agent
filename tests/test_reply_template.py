"""The auto-responder must prefer the tenant's editable reply template.

Without this, a workspace that seeded a ``reply`` template would still answer
with the hardcoded Python body, and editing the template in the dashboard would
appear to do nothing.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agents
from app.db import Base, Contact, Settings, Template


def _make_responder(monkeypatch, *, reply_template_body=None, reply_template_subject=None):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(agents, "SessionLocal", session_factory)

    db = session_factory()
    contact = Contact(email="lead@example.com", eligible_to_email=True, tenant_id=1)
    db.add(contact)
    db.add(Settings(tenant_id=1, business_name="Acme"))
    if reply_template_body is not None:
        db.add(
            Template(
                tenant_id=1,
                name="Reply",
                category="reply",
                subject_template=reply_template_subject or "Re: {{ subject }}",
                body_template=reply_template_body,
                is_active=True,
            )
        )
    db.commit()
    contact_id = contact.id
    db.close()

    responder = agents.AutoResponder(contact_id=contact_id)
    return responder, session_factory, engine


def test_reply_uses_db_template_when_present(monkeypatch):
    responder, session_factory, engine = _make_responder(
        monkeypatch,
        reply_template_body="Hi {{ first_name }}, custom reply body from the dashboard.",
        reply_template_subject="Re: {{ subject }}",
    )
    try:
        result = responder.generate_response(
            classification={"reply_type": "positive_response", "event_id": 7},
            original_subject="Introduction",
            original_body="Interested",
            sender_email="lead@example.com",
        )
        assert result is not None
        assert "custom reply body from the dashboard" in result["body"]
        # The subject template is honoured too, with the original subject merged.
        assert result["subject"] == "Re: Introduction"
    finally:
        responder.close()
        engine.dispose()


def test_reply_falls_back_to_hardcoded_template_without_db_row(monkeypatch):
    responder, session_factory, engine = _make_responder(monkeypatch, reply_template_body=None)
    try:
        result = responder.generate_response(
            classification={"reply_type": "question", "event_id": 8},
            original_subject="Question",
            original_body="How much?",
            sender_email="lead@example.com",
        )
        assert result is not None
        assert result["subject"].startswith("Re:")
        assert result["body"].strip() != ""
    finally:
        responder.close()
        engine.dispose()


def test_provisioning_backfills_reply_template_for_existing_tenant(monkeypatch):
    """A workspace created before the reply template existed still gets one."""
    from app.services import provisioning

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()

    # Seed an old-style workspace: intro + followup only, no reply.
    db.add(Settings(tenant_id=1))
    db.add(Template(tenant_id=1, name="Intro Email", category="intro",
                    subject_template="A quick introduction", body_template="Hi"))
    db.add(Template(tenant_id=1, name="Follow-up", category="followup",
                    subject_template="Following up", body_template="Hi"))
    db.commit()

    provisioning.provision_tenant_defaults(db, tenant_id=1, inherit_environment=False)

    rows = db.query(Template).filter(Template.tenant_id == 1).all()
    categories = {r.category for r in rows}
    assert "reply" in categories
    db.close()
    engine.dispose()