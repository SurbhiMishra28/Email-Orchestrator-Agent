"""Deleting a draft.

A sent draft is the only record that a message left the mailbox, so it must not
be deletable; an unsent one must be.
"""
import uuid


def _headers(client):
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/auth/register",
        json={
            "email": f"draft-{suffix}@example.org",
            "password": "draft-password-123",
            "name": "Draft User",
            "tenant_name": f"Draft Tenant {suffix}",
        },
    )
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _contact(client, headers):
    r = client.post(
        "/api/contacts",
        json={"email": f"lead-{uuid.uuid4().hex[:6]}@example.com", "name": "Lead"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_unsent_draft_can_be_deleted(client):
    headers = _headers(client)
    cid = _contact(client, headers)

    created = client.post(
        "/api/drafts/compose",
        json={"contact_id": cid, "subject": "Delete me", "body": "Body"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    draft_id = created.json()["id"]

    deleted = client.delete(f"/api/drafts/{draft_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    remaining = client.get("/api/drafts", headers=headers).json()
    assert all(d["id"] != draft_id for d in remaining)


def test_sent_draft_cannot_be_deleted(client):
    headers = _headers(client)
    cid = _contact(client, headers)

    created = client.post(
        "/api/drafts/compose",
        json={"contact_id": cid, "subject": "Sent", "body": "Body"},
        headers=headers,
    )
    draft_id = created.json()["id"]

    db = __import__("app.db", fromlist=["SessionLocal", "Draft"]).SessionLocal()
    try:
        row = db.query(__import__("app.db", fromlist=["Draft"]).Draft).filter(
            __import__("app.db", fromlist=["Draft"]).Draft.id == draft_id
        ).one()
        row.status = "sent"
        db.commit()
    finally:
        db.close()

    response = client.delete(f"/api/drafts/{draft_id}", headers=headers)
    assert response.status_code == 409, response.text


def test_deleting_another_tenants_draft_is_404(client):
    headers = _headers(client)
    cid = _contact(client, headers)
    created = client.post(
        "/api/drafts/compose",
        json={"contact_id": cid, "subject": "Mine", "body": "Body"},
        headers=headers,
    )
    draft_id = created.json()["id"]

    other = _headers(client)
    assert client.delete(f"/api/drafts/{draft_id}", headers=other).status_code == 404