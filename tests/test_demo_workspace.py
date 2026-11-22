"""The shared demo workspace must be usable, and safe on its own terms.

The demo account is handed out by the app itself, so its safety cannot rest on a
visitor's goodwill. These tests cover the invariants that matter:

* the workspace looks alive and is reachable without credentials,
* sending is available (``DEMO_ALLOW_SENDING``), but on terms that cannot hurt the
  operator: the demo never inherits the deployment's SMTP credentials and never
  reads the deployment's mailbox,
* setting ``DEMO_ALLOW_SENDING=false`` puts every relay path back behind 403.
"""
import pytest

from app.config import settings as app_settings
from app.db import Draft, SMTPConfig, SessionLocal, Tenant
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


def test_demo_never_inherits_the_operator_smtp(client):
    """The demo is public, so the deployment's own relay must not reach it."""
    seed_demo_workspace()
    db = SessionLocal()
    try:
        tenant_id = db.query(Tenant.id).filter(Tenant.subdomain == DEMO_SUBDOMAIN).one()[0]
        smtp = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == tenant_id).one()
        assert not smtp.host
        assert not smtp.user
        assert not smtp.password
        assert smtp.configured is False
    finally:
        db.close()


def test_demo_can_open_a_smtp_config(demo_client):
    """Sending is on, so the settings form must be usable."""
    session, _user = demo_client
    assert app_settings.DEMO_ALLOW_SENDING is True
    response = session.get("/api/smtp/status")
    assert response.status_code == 200
    # Nothing is configured for the operator's account, so a visitor brings their
    # own relay or nothing sends at all.
    assert response.json()["configured"] is False


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/inbox/sync", None),
    ],
)
def test_demo_cannot_read_the_operator_mailbox(demo_client, path, payload):
    """IMAP credentials are deployment-wide, so the demo is always refused."""
    session, _user = demo_client
    response = session.post(path, json=payload) if payload is not None else session.post(path)
    assert response.status_code == 403, f"{path} -> {response.status_code} {response.text}"


def test_demo_login_is_public(client):
    """No token is required: the app opens the demo workspace on first load."""
    anonymous = client.__class__(client.app)
    response = anonymous.post("/api/auth/demo")
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_demo_can_send_with_its_own_relay(demo_client):
    """Sending is enabled: a visitor who configures a relay can complete a send.

    ``MAIL_SUPPRESS_SEND`` is on for the suite, so no message leaves the machine;
    this only proves the demo guard is not what stops the send.
    """
    session, _user = demo_client
    db = SessionLocal()
    try:
        tenant_id = db.query(Tenant.id).filter(Tenant.subdomain == DEMO_SUBDOMAIN).one()[0]
        draft = (
            db.query(Draft)
            .filter(Draft.tenant_id == tenant_id, Draft.status.in_(["draft", "failed"]))
            .first()
        )
        assert draft is not None
        draft_id = draft.id
    finally:
        db.close()

    saved = session.post(
        "/api/smtp/config",
        json={
            "host": "smtp.example.com",
            "port": 587,
            "user": "demo@example.com",
            "password": "demo-password",
            "sender": "demo@example.com",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["configured"] is True

    try:
        response = session.post(f"/api/drafts/{draft_id}/send")
        assert response.status_code != 403, response.text
        assert response.status_code == 200, response.text
    finally:
        # Leave the shared workspace as the seeder created it.
        db = SessionLocal()
        try:
            smtp = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == tenant_id).one()
            smtp.host = ""
            smtp.user = ""
            smtp.password = ""
            smtp.sender = ""
            smtp.configured = False
            smtp.authentication_configured = False
            db.commit()
        finally:
            db.close()


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/smtp/config", {"host": "smtp.example.com", "port": 587, "user": "u", "password": "p", "sender": "u@example.com"}),
        ("/api/smtp/test", {"host": "smtp.example.com", "port": 587}),
        ("/api/queue/run", None),
        ("/api/queue/run-all", {}),
        ("/api/queue/run-async", {}),
        ("/api/scheduling/run-now", None),
        ("/api/scheduling/autopilot", {"enabled": True}),
        ("/api/run", {}),
    ],
)
def test_read_only_mode_refuses_every_relay_path(monkeypatch, demo_client, path, payload):
    """``DEMO_ALLOW_SENDING=false`` restores the original read-only workspace."""
    monkeypatch.setattr(app_settings, "DEMO_ALLOW_SENDING", False)
    session, _user = demo_client
    response = session.post(path, json=payload) if payload is not None else session.post(path)
    assert response.status_code == 403, f"{path} -> {response.status_code} {response.text}"


def test_read_only_mode_refuses_a_draft_send(monkeypatch, demo_client):
    monkeypatch.setattr(app_settings, "DEMO_ALLOW_SENDING", False)
    session, _user = demo_client
    drafts = session.get("/api/state").json()["drafts"]
    assert drafts
    response = session.post(f"/api/drafts/{drafts[0]['id']}/send")
    assert response.status_code == 403


def test_read_only_mode_does_not_affect_normal_tenants(monkeypatch, client):
    """The switch is about the shared workspace, not about everyone."""
    monkeypatch.setattr(app_settings, "DEMO_ALLOW_SENDING", False)
    response = client.get("/api/smtp/status")
    assert response.status_code == 200


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
