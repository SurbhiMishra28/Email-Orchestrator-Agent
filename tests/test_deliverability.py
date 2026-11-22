"""Tests for the "only real addresses" rules.

Autopilot sends without a human, so the send paths must refuse an address that
can never receive mail instead of recording a relay-accepted "sent". And because
Gmail accepts a message before it knows the mailbox is dead, the only hard
evidence of a bad address is the bounce that follows: a DSN must blacklist the
contact so no future pass drafts for it again.
"""
import asyncio
import uuid

import pytest

import app.agents
from app import main as app_main
from app.db import Contact, Draft, InboxMessage, SessionLocal
from app.services import recipients


def test_reserved_domains_are_never_mailable():
    for address in (
        "someone@example.com",
        "someone@example.org",
        "someone@test.com",
        "someone@mail.example",
        "someone@host.invalid",
        "someone@localhost",
    ):
        assert recipients.address_problem(address), address


def test_real_business_address_is_mailable():
    assert recipients.address_problem("surbhi.m2805@gmail.com") is None
    assert recipients.address_problem("first.last@skorainfotech.com") is None


def test_mail_system_and_disposable_mailboxes_are_refused():
    assert recipients.address_problem("mailer-daemon@googlemail.com")
    assert recipients.address_problem("postmaster@gmail.com")
    assert recipients.address_problem("someone@yopmail.com")


def test_sender_own_address_is_refused():
    problem = recipients.address_problem(
        "surbhi.m2805@gmail.com", sender_email="surbhi.m2805@gmail.com"
    )
    assert problem and "own address" in problem


def test_guard_flag_disables_all_checks(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "BLOCK_PLACEHOLDER_RECIPIENTS", False)
    assert recipients.blocked_reason("someone@example.com") is None


def _tenant_id(headers):
    token = headers["Authorization"].split(" ", 1)[1]
    from jose import jwt

    from app.auth import ALGORITHM, SECRET_KEY

    return int(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["tenant_id"])


def _new_tenant(client):
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"deliver-{suffix}@example.com",
            "password": "deliver-password-123",
            "name": "Deliverability User",
            "tenant_name": f"Deliverability {suffix}",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_contact_creation_refuses_a_placeholder_address(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "BLOCK_PLACEHOLDER_RECIPIENTS", True)
    headers = _new_tenant(client)

    response = client.post(
        "/api/contacts",
        json={"email": "placeholder@example.com", "eligible_to_email": True},
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert "reserved" in response.json()["detail"].lower()


def test_csv_import_skips_placeholder_rows(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "BLOCK_PLACEHOLDER_RECIPIENTS", True)
    headers = _new_tenant(client)

    response = client.post(
        "/api/contacts/import",
        json={
            "csv": (
                "email,name\n"
                "real.person@acme-corp.io,Real Person\n"
                "fake.person@example.com,Fake Person\n"
            ),
            "default_eligible": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 1, body
    assert any("example.com" in error for error in body["errors"]), body


def test_queue_fails_a_placeholder_draft_and_blacklists_the_contact(
    client, monkeypatch
):
    """A draft that already exists for a placeholder must never be sent."""
    from app.config import settings

    monkeypatch.setattr(settings, "BLOCK_PLACEHOLDER_RECIPIENTS", True)
    headers = _new_tenant(client)
    tenant_id = _tenant_id(headers)

    db = SessionLocal()
    try:
        contact = Contact(
            tenant_id=tenant_id,
            email=f"ghost-{uuid.uuid4().hex[:8]}@example.com",
            name="Ghost",
            eligible_to_email=True,
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        draft = Draft(
            tenant_id=tenant_id,
            contact_id=contact.id,
            subject="Hello",
            body="Body",
            status="draft",
        )
        db.add(draft)
        db.commit()
        contact_id, draft_id = contact.id, draft.id
    finally:
        db.close()

    sent = []
    monkeypatch.setattr(
        app.agents, "send_email", lambda *a, **k: sent.append(a) or "<id>"
    )
    monkeypatch.setattr(
        "app.services.mailer.is_configured", lambda *a, **k: True
    )
    monkeypatch.setattr(
        app.agents, "is_configured", lambda *a, **k: True
    )

    result = asyncio.run(app.agents.QueueManager().process_queue(tenant_id=tenant_id))

    assert sent == [], sent
    assert result["failed"] == 1, result

    db = SessionLocal()
    try:
        saved_draft = db.query(Draft).filter(Draft.id == draft_id).first()
        saved_contact = db.query(Contact).filter(Contact.id == contact_id).first()
        assert saved_draft.status == "failed", saved_draft.status
        assert "reserved" in (saved_draft.error_message or "").lower()
        assert saved_contact.email_blacklisted is True
        assert saved_contact.eligible_to_email is False
    finally:
        db.close()


def test_bounce_notification_blacklists_the_failed_recipient(monkeypatch):
    """A DSN in the inbox must make the dead address unmailable for good."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(app_main, "SessionLocal", factory)
    monkeypatch.setattr(app.agents, "SessionLocal", factory)

    dead = f"dead-{uuid.uuid4().hex[:8]}@gone-corp.com"
    db = factory()
    try:
        contact = Contact(tenant_id=1, email=dead, name="Dead", eligible_to_email=True)
        db.add(contact)
        db.commit()
        db.refresh(contact)
        db.add(
            Draft(
                tenant_id=1,
                contact_id=contact.id,
                subject="Intro",
                body="Body",
                status="sent",
            )
        )
        db.add(
            InboxMessage(
                tenant_id=1,
                uid="9001",
                sender="Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                subject="Delivery Status Notification (Failure)",
                snippet=(
                    "Address not found. Your message wasn't delivered to "
                    f"{dead} because the address couldn't be found."
                ),
            )
        )
        db.commit()
        contact_id = contact.id
    finally:
        db.close()

    queued = asyncio.run(app_main._process_incoming_replies(tenant_id=1))

    # A bounce is not a conversation: nothing may be auto-answered.
    assert queued == 0, queued

    db = factory()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        assert contact.email_blacklisted is True
        assert contact.eligible_to_email is False
        message = db.query(InboxMessage).filter(InboxMessage.uid == "9001").first()
        assert message.processed is True
    finally:
        db.close()
        engine.dispose()
