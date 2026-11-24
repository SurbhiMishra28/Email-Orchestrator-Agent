"""Regression tests for batch sending from the campaign / "send selected" paths.

``/api/queue/run-all`` used to make a single queue pass, so under the 60-second
pacing rule a click delivered exactly one email. It now drains the queue and
hands anything left to the background worker.
"""
import uuid

import pytest

from app.db import Contact, Draft, SessionLocal, Template


def _fresh_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"batch-{suffix}@example.com",
            "password": "batch-password-123",
            "name": "Batch User",
            "tenant_name": f"Batch Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


@pytest.fixture
def sent_mail(monkeypatch):
    """Capture sends instead of talking to a real SMTP server."""
    import app.agents as agents

    sent = []

    def fake_send(smtp_config, to_email, subject, body, *args, **kwargs):
        sent.append(to_email)
        return "<test-message-id>"

    monkeypatch.setattr(agents, "send_email", fake_send)
    return sent


def _tenant_id(headers):
    token = headers["Authorization"].split(" ", 1)[1]
    from jose import jwt

    from app.auth import ALGORITHM, SECRET_KEY
    from app.db import User

    # ``sub`` is the user id, not the tenant id; resolve the tenant through the
    # user row so the assertion does not depend on the two ids coinciding.
    user_id = int(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"])
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).one().tenant_id
    finally:
        db.close()


def _seed_contacts_and_template(client, headers, count=3):
    """Three eligible contacts plus one intro template for the caller's tenant."""
    suffix = uuid.uuid4().hex[:8]
    contact_ids = []
    for index in range(count):
        created = client.post(
            "/api/contacts",
            json={
                "email": f"batch-{suffix}-{index}@example.com",
                "name": f"Batch {index}",
                "eligible_to_email": True,
            },
            headers=headers,
        )
        assert created.status_code == 200, created.text
        contact_ids.append(created.json()["id"])

    template = client.post(
        "/api/templates",
        json={
            "name": f"Batch intro {suffix}",
            "category": "intro",
            "subject_template": "Quick intro",
            "body_template": "Hi {{first_name or 'there'}}, a short note.",
        },
        headers=headers,
    )
    assert template.status_code in (200, 201), template.text
    return contact_ids, template.json()["id"]


def test_run_all_drains_a_paced_queue(client, monkeypatch, sent_mail):
    """A single /run-all call must deliver the whole ready batch, not one email."""
    from app.services import limits

    # The pacing window is 60s in production; the drain must not spend it here.
    monkeypatch.setattr(limits, "PACING_SECONDS", 0)

    headers = _fresh_headers(client)
    contact_ids, template_id = _seed_contacts_and_template(client, headers)

    response = client.post(
        "/api/queue/run-all",
        json={"template_id": template_id, "contact_ids": contact_ids},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drafts_created"] == len(contact_ids), body
    result = body["result"]
    assert result["sent"] == len(contact_ids), result
    assert len(sent_mail) == len(contact_ids), sent_mail
    # Everything went out inline, so no follow-up job was needed.
    assert body["queued"] is False, body
    assert body["job_id"] is None, body


def test_run_all_leaves_no_draft_behind_unattended(client, monkeypatch, sent_mail):
    """Every created draft ends up sent, not stranded waiting for another click."""
    from app.services import limits

    monkeypatch.setattr(limits, "PACING_SECONDS", 0)

    headers = _fresh_headers(client)
    contact_ids, template_id = _seed_contacts_and_template(client, headers, count=2)
    tenant_id = _tenant_id(headers)

    response = client.post(
        "/api/queue/run-all",
        json={"template_id": template_id, "contact_ids": contact_ids},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    db = SessionLocal()
    try:
        drafts = db.query(Draft).filter(Draft.tenant_id == tenant_id).all()
        assert len(drafts) == len(contact_ids), len(drafts)
        assert {draft.status for draft in drafts} == {"sent"}, [
            draft.status for draft in drafts
        ]
    finally:
        db.close()

    assert not body["queued"], body


def test_run_all_reports_zero_when_nothing_is_eligible(client):
    headers = _fresh_headers(client)
    contact = client.post(
        "/api/contacts",
        json={
            "email": f"ineligible-{uuid.uuid4().hex[:8]}@example.com",
            "name": "Ineligible",
            "eligible_to_email": False,
        },
        headers=headers,
    )
    assert contact.status_code == 200, contact.text

    template = client.post(
        "/api/templates",
        json={
            "name": f"Zero {uuid.uuid4().hex[:8]}",
            "category": "intro",
            "subject_template": "Hi",
            "body_template": "Body",
        },
        headers=headers,
    )
    assert template.status_code in (200, 201), template.text

    response = client.post(
        "/api/queue/run-all",
        json={"template_id": template.json()["id"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drafts_created"] == 0, body
    assert body["result"]["sent"] == 0, body
