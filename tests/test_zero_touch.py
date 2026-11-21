"""Regression tests for the zero-touch pipeline.

Covers the three things that used to stop a "add contacts, press Run" flow:

* template aliases, so a tenant whose template is called "Personalized Mail"
  is not treated as having no intro template,
* the queue draining instead of stopping after one paced send, and
* CSV imports without an ``email_permission`` column being usable.
"""
import asyncio
import uuid

import pytest

from app.services import outreach
from app.services.send_worker import drain_queue


def _new_tenant_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"zero-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Zero Touch",
            "tenant_name": f"Zero Touch {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def test_import_without_permission_column_is_eligible(client):
    """A plain email,name CSV must not import contacts that can never be sent."""
    headers = _new_tenant_headers(client)
    email = f"noperm-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/api/contacts/import",
        json={"csv": f"email,name\n{email},No Perm\n"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    contacts = client.get("/api/contacts", headers=headers).json()
    imported = next(c for c in contacts if c["email"] == email)
    assert imported["eligible_to_email"] is True


def test_import_can_opt_out_of_default_eligibility(client):
    headers = _new_tenant_headers(client)
    email = f"paused-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/api/contacts/import",
        json={"csv": f"email,name\n{email},Paused\n", "default_eligible": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    contacts = client.get("/api/contacts", headers=headers).json()
    imported = next(c for c in contacts if c["email"] == email)
    assert imported["eligible_to_email"] is False


def test_import_permission_column_still_wins(client):
    headers = _new_tenant_headers(client)
    opted_out = f"optout-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/api/contacts/import",
        json={"csv": f"email,name,email_permission\n{opted_out},Opted Out,false\n"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    contacts = client.get("/api/contacts", headers=headers).json()
    imported = next(c for c in contacts if c["email"] == opted_out)
    assert imported["eligible_to_email"] is False


def test_drain_sends_every_sendable_draft(client, monkeypatch):
    """One drain must not stop at the first paced send."""
    from app.agents import QueueManager
    from app.services import limits

    # The real pacing gap is 60s; waiting it out would make the test hang.
    monkeypatch.setattr(limits, "PACING_SECONDS", 0)

    calls = []

    async def fake_process_queue(self, tenant_id=None):
        # Model a queue that is paced: the first two passes each report a pause
        # after one send, then it is empty.
        if len(calls) < 3:
            calls.append(1)
            details = [{"status": "sent"}]
            if len(calls) < 3:
                details.append({"status": "paused", "reason": "Pacing: wait 60s"})
            return {
                "processed": 1,
                "sent": 1,
                "failed": 0,
                "skipped": 0,
                "details": details,
            }
        return {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []}

    original = QueueManager.process_queue
    QueueManager.process_queue = fake_process_queue
    try:
        result = asyncio.run(drain_queue(tenant_id=1, max_seconds=1))
    finally:
        QueueManager.process_queue = original

    assert result["sent"] == 3, result
    assert result["passes"] >= 3, result


def test_drain_stops_when_nothing_can_be_sent(client):
    from app.agents import QueueManager

    async def blocked_process_queue(self, tenant_id=None):
        return {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 2,
            "details": [{"status": "skipped", "reason": "SMTP is not configured"}],
        }

    original = QueueManager.process_queue
    QueueManager.process_queue = blocked_process_queue
    try:
        result = asyncio.run(drain_queue(tenant_id=1, max_seconds=5))
    finally:
        QueueManager.process_queue = original

    # A blocked pass must not loop: one pass, no sends, no pause.
    assert result["sent"] == 0
    assert result["passes"] == 1
    assert result["paused"] is False


def test_intro_template_alias_is_resolved():
    """A tenant whose intro template uses a legacy category still gets drafts."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, Contact, Draft, Template
    import app.agents

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    original_session = outreach.SessionLocal
    original_agent_session = app.agents.SessionLocal
    original_expand = app.agents.expand_template_with_ai

    async def expand_template(template, contact):
        return {"subject": "Hello", "body": "Body"}

    outreach.SessionLocal = session_factory
    app.agents.SessionLocal = session_factory
    app.agents.expand_template_with_ai = expand_template
    try:
        db = session_factory()
        # The legacy spelling written by init_templates.py, never "intro".
        db.add(
            Template(
                tenant_id=7,
                name="Personalized Mail",
                category="personalized_mail",
                subject_template="Hi",
                body_template="Body",
                is_active=True,
            )
        )
        db.add(
            Contact(
                tenant_id=7,
                email="alias@example.com",
                name="Alias",
                eligible_to_email=True,
            )
        )
        db.commit()
        db.close()

        result = asyncio.run(outreach.create_intro_drafts(tenant_id=7))

        assert result["created"] == 1, result
        db = session_factory()
        try:
            assert db.query(Draft).count() == 1
        finally:
            db.close()
    finally:
        outreach.SessionLocal = original_session
        app.agents.SessionLocal = original_agent_session
        app.agents.expand_template_with_ai = original_expand
        engine.dispose()
