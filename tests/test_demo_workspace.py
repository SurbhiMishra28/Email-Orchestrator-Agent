"""The shared demo workspace must be usable but unable to send or store secrets.

The demo account is handed out by the sign-in screen, so its safety cannot rest
on a visitor's goodwill. These tests cover the two invariants that matter: the
workspace looks alive, and every path that could reach a mail relay refuses.
"""
import pytest

from app.db import SessionLocal, Tenant
from app.services.demo import (
    DEMO_EMAIL,
    DEMO_SUBDOMAIN,
    is_demo_tenant,
    seed_demo_workspace,
)


@pytest.fixture(scope="module")
def demo_client(client):
    """A TestClient authenticated as the shared demo account.

    ``client`` registers a normal tenant first, so this also proves the demo can
    coexist with real accounts in one database.
    """
    response = client.post("/api/auth/demo")
    assert response.status_code == 200, response.text
    body = response.json()

    session = client.__class__(client.app)
    session.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    yield session, body["user"]


def test_demo_login_returns_demo_identity(demo_client):
    _client, user = demo_client
    assert user["email"] == DEMO_EMAIL
    assert user["demo"] is True
    assert user["tenant"]["name"]


def test_demo_me_is_flagged(client, demo_client):
    session, _user = demo_client
    me = session.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["demo"] is True
    # A normal account must not be mislabelled as the demo.
    assert client.get("/api/auth/me").json()["demo"] is False


def test_demo_workspace_has_seeded_content(demo_client):
    session, _user = demo_client
    state = session.get("/api/state").json()

    assert len(state["contacts"]) >= 10
    assert state["drafts"]
    assert state["analytics"]["sent"] > 0
    assert state["analytics"]["replied"] > 0
    # An unconfigured inbox/relay is what stops the workspace from sending.
    assert state["smtp"]["configured"] is False

    for path, minimum in (
        ("/api/lists", 2),
        ("/api/campaigns", 1),
        ("/api/verifications", 1),
    ):
        response = session.get(path)
        assert response.status_code == 200, path
        data = response.json()
        rows = data if isinstance(data, list) else data.get("messages", [])
        assert len(rows) >= minimum, path


def test_demo_seed_is_idempotent(client):
    """Re-seeding must not duplicate contacts, drafts or events."""
    session, _user = client.__class__(client.app), None
    first = session.post("/api/auth/demo").json()
    session.headers.update({"Authorization": f"Bearer {first['access_token']}"})

    before = session.get("/api/state").json()
    seed_demo_workspace()
    after = session.get("/api/state").json()

    assert len(before["contacts"]) == len(after["contacts"])
    assert len(before["drafts"]) == len(after["drafts"])


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/smtp/config", {"host": "smtp.example.com", "port": 587, "user": "u", "password": "p", "sender": "u@example.com"}),
        ("/api/smtp/test", {"host": "smtp.example.com", "port": 587}),
        ("/api/inbox/sync", None),
        ("/api/queue/run", None),
        ("/api/queue/run-all", {}),
        ("/api/queue/run-async", {}),
        ("/api/scheduling/run-now", None),
        ("/api/scheduling/autopilot", {"enabled": True}),
        ("/api/run", {}),
    ],
)
def test_demo_cannot_reach_a_mail_relay(demo_client, path, payload):
    session, _user = demo_client
    response = session.post(path, json=payload) if payload is not None else session.post(path)
    assert response.status_code == 403, f"{path} -> {response.status_code} {response.text}"


def test_demo_cannot_send_a_draft(demo_client):
    session, _user = demo_client
    drafts = session.get("/api/state").json()["drafts"]
    assert drafts
    response = session.post(f"/api/drafts/{drafts[0]['id']}/send")
    assert response.status_code == 403


def test_demo_login_is_public(client):
    """No token is required: that is the whole point of the demo button."""
    anonymous = client.__class__(client.app)
    response = anonymous.post("/api/auth/demo")
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_is_demo_tenant_distinguishes_tenants(client):
    db = SessionLocal()
    try:
        demo_id = db.query(Tenant.id).filter(Tenant.subdomain == DEMO_SUBDOMAIN).one()[0]
        other_id = db.query(Tenant.id).filter(Tenant.subdomain != DEMO_SUBDOMAIN).first()[0]
        assert is_demo_tenant(db, demo_id) is True
        assert is_demo_tenant(db, other_id) is False
        assert is_demo_tenant(db, None) is False
    finally:
        db.close()
