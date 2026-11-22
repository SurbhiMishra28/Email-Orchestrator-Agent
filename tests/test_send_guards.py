"""Regression tests for the guard-rails on the direct send paths.

Three separate holes are covered:

* ``POST /api/agents/send`` used to talk to SMTP with no draft, no usage row and
  no cap check, so it could send unlimited unmetered mail.
* A JWT stayed usable after its account was deactivated, because only
  ``/api/auth/login`` looked at ``is_active``.
* Reply de-duplication keyed on the bare IMAP UID, but UIDs are unique per
  mailbox only, so two tenants both starting at UID 1 suppressed each other.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.agents
from app import main as app_main
from app.db import (
    Base,
    Contact,
    Draft,
    InboxMessage,
    SessionLocal,
    UsageLog,
    User,
)


@pytest.fixture
def isolated_db(monkeypatch):
    """Point the reply pipeline at one in-memory database.

    Only ``app.main`` and ``app.agents`` are patched: those are the modules the
    reply processing reads. Router modules keep their own ``SessionLocal`` and are
    exercised through the API against the suite database instead.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(app_main, "SessionLocal", factory)
    monkeypatch.setattr(app.agents, "SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()


def _direct_send(client, headers, to_email, subject="Hello"):
    return client.post(
        "/api/agents/send",
        json={"to_email": to_email, "subject": subject, "body": "Body"},
        headers=headers,
    )


def test_agents_send_refuses_a_recipient_that_is_not_a_contact(client, monkeypatch):
    """An address outside the workspace must not be sendable anonymously."""
    headers = _new_tenant(client)
    address = f"known-{uuid.uuid4().hex[:8]}@example.com"
    _add_contact(client, headers, address)
    _configure_workspace(client, headers)

    monkeypatch.setattr(
        "app.routers.agents.send_email",
        lambda *args, **kwargs: "<sent@example.com>",
    )

    response = _direct_send(client, headers, f"stranger-{uuid.uuid4().hex[:8]}@example.com")

    assert response.status_code == 404
    assert "contact" in response.json()["detail"].lower()


def _new_tenant(client):
    """Register a fresh tenant so its send counters and pacing start empty."""
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"guards-{suffix}@example.com",
            "password": "guards-password-123",
            "name": "Guards User",
            "tenant_name": f"Guards Tenant {suffix}",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _configure_workspace(client, headers, daily_cap=500, domain_cap=50):
    """Give the caller's tenant SMTP details and a cap, through the real API."""
    response = client.post(
        "/api/smtp/config",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "user": "sender@example.com",
            "password": "secret",
            "sender": "sender@example.com",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/settings",
        json={"daily_cap": daily_cap, "domain_cap": domain_cap},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _add_contact(client, headers, address):
    response = client.post(
        "/api/contacts",
        json={"email": address, "name": "Lead", "eligible_to_email": True},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_agents_send_records_a_draft_and_usage(client, monkeypatch):
    """A successful direct send is metered like a queue send."""
    headers = _new_tenant(client)
    address = f"lead-{uuid.uuid4().hex[:8]}@example.com"
    _add_contact(client, headers, address)
    _configure_workspace(client, headers)
    tenant_id = client.get("/api/auth/me", headers=headers).json()["tenant"]["id"]

    monkeypatch.setattr(
        "app.routers.agents.send_email",
        lambda *args, **kwargs: "<sent@example.com>",
    )

    response = _direct_send(client, headers, address)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["draft_id"]

    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.id == body["draft_id"]).one()
        assert draft.status == "sent"
        assert draft.sent_at is not None
        assert draft.tenant_id == tenant_id
        assert (
            db.query(UsageLog)
            .filter(UsageLog.tenant_id == tenant_id, UsageLog.metric == "emails_sent")
            .count()
            == 1
        )
    finally:
        db.close()


def test_agents_send_respects_the_daily_cap(client, monkeypatch):
    """The direct endpoint cannot be used to blow past the daily cap."""
    headers = _new_tenant(client)
    address = f"capped-{uuid.uuid4().hex[:8]}@example.com"
    _add_contact(client, headers, address)
    _configure_workspace(client, headers, daily_cap=1, domain_cap=50)

    sent = []
    monkeypatch.setattr(
        "app.routers.agents.send_email",
        lambda *args, **kwargs: sent.append(args) or "<sent@example.com>",
    )

    assert _direct_send(client, headers, address).status_code == 200
    blocked = _direct_send(client, headers, address)

    assert blocked.status_code == 429, blocked.text
    assert "cap" in blocked.json()["detail"].lower()
    assert len(sent) == 1


def test_deactivated_account_cannot_use_an_existing_token(client):
    """Deactivating a user must invalidate the token it already holds."""
    from app.auth import create_access_token, hash_password

    email = f"paused-{uuid.uuid4().hex[:8]}@example.com"
    db = SessionLocal()
    try:
        user = User(
            tenant_id=1,
            email=email,
            hashed_password=hash_password("paused-password-123"),
            name="Paused",
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(data={"sub": user.id, "tenant_id": user.tenant_id})
        user_id = user.id
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    db = SessionLocal()
    try:
        db.query(User).filter(User.id == user_id).update({"is_active": False})
        db.commit()
    finally:
        db.close()

    assert client.get("/api/auth/me", headers=headers).status_code == 403


def test_same_imap_uid_in_two_mailboxes_is_processed_for_both(isolated_db):
    """UID 101 in tenant A must not mask UID 101 in tenant B."""
    db = isolated_db()
    try:
        for tenant_id, address in ((1, "lead@alpha.example"), (2, "lead@beta.example")):
            db.add(
                Contact(tenant_id=tenant_id, email=address, name="Lead", eligible_to_email=True)
            )
            db.add(
                InboxMessage(
                    tenant_id=tenant_id,
                    uid="101",
                    sender=f"Lead <{address}>",
                    subject="Re: Intro",
                    snippet="Yes, I'm interested, let's talk.",
                )
            )
        db.commit()
    finally:
        db.close()

    queued = asyncio.run(app_main._process_incoming_replies())

    assert queued == 2
    db = isolated_db()
    try:
        tenants = {draft.tenant_id for draft in db.query(Draft).all()}
        assert tenants == {1, 2}
    finally:
        db.close()
