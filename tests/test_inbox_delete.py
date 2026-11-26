"""Deleting a stored inbox message.

The local copy can be removed; the message in the IMAP mailbox is untouched.
"""
import uuid

from app.db import InboxMessage, SessionLocal, Tenant


def _headers(client):
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/auth/register",
        json={
            "email": f"inbox-{suffix}@example.org",
            "password": "inbox-password-123",
            "name": "Inbox User",
            "tenant_name": f"Inbox Tenant {suffix}",
        },
    )
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_message(tenant_id: int) -> int:
    db = SessionLocal()
    try:
        message = InboxMessage(
            tenant_id=tenant_id,
            uid=f"uid-{uuid.uuid4().hex[:8]}",
            sender="lead@example.com",
            subject="Hello",
            snippet="Body",
        )
        db.add(message)
        db.commit()
        return message.id
    finally:
        db.close()


def _tenant_id(headers) -> int:
    """Resolve the caller's tenant from the DB.

    The JWT ``sub`` is the *user* id, which only coincides with the tenant id on
    a fresh database. Looking it up keeps this correct once the suite has created
    many tenants.
    """
    import base64
    import json

    token = headers["Authorization"].split(" ", 1)[1]
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    user_id = int(json.loads(base64.urlsafe_b64decode(payload))["sub"])

    from app.db import User

    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).one().tenant_id
    finally:
        db.close()


def test_delete_stored_message(client):
    headers = _headers(client)
    tid = _tenant_id(headers)
    message_id = _seed_message(tid)

    response = client.delete(f"/api/inbox/messages/{message_id}", headers=headers)
    assert response.status_code == 200, response.text

    db = SessionLocal()
    try:
        assert db.query(InboxMessage).filter(InboxMessage.id == message_id).first() is None
    finally:
        db.close()


def test_cannot_delete_another_tenants_message(client):
    headers = _headers(client)
    tid = _tenant_id(headers)
    message_id = _seed_message(tid)

    other = _headers(client)
    assert client.delete(f"/api/inbox/messages/{message_id}", headers=other).status_code == 404


def test_deleting_a_missing_message_is_404(client):
    headers = _headers(client)
    assert client.delete("/api/inbox/messages/999999", headers=headers).status_code == 404