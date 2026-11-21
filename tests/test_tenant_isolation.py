"""Cross-tenant isolation and auth-enforcement tests.

These are the acceptance tests for the tenant-scoping work: two accounts must
never see each other's rows, and every resource router must reject anonymous
callers.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _register(client: TestClient, label: str) -> dict:
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "email": f"{label}-{suffix}@example.com",
        "password": "tenant-password-123",
        "name": f"{label.title()} User",
        "tenant_name": f"{label.title()} Tenant {suffix}",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200, response.text
    return {
        "token": response.json()["access_token"],
        "headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
        "email": payload["email"],
        "tenant_name": payload["tenant_name"],
    }


@pytest.fixture(scope="module")
def two_tenants(client):
    # Reuse the session client's lifespan (DB/schema ready) but send explicit
    # per-request headers so each tenant is isolated within the same app.
    first = _register(client, "alpha")
    second = _register(client, "beta")
    yield client, first, second


def test_contacts_are_isolated_between_tenants(two_tenants):
    client, alpha, beta = two_tenants

    created = client.post(
        "/api/contacts",
        json={"email": f"alpha-lead-{uuid.uuid4().hex[:6]}@example.com", "name": "Alpha Lead"},
        headers=alpha["headers"],
    )
    assert created.status_code == 200, created.text
    contact_id = created.json()["id"]

    alpha_list = client.get("/api/contacts", headers=alpha["headers"])
    assert any(c["id"] == contact_id for c in alpha_list.json())

    beta_list = client.get("/api/contacts", headers=beta["headers"])
    assert all(c["id"] != contact_id for c in beta_list.json())

    # Direct access by id must 404, not leak the row.
    assert client.get(f"/api/contacts/{contact_id}", headers=beta["headers"]).status_code == 404
    assert client.patch(
        f"/api/contacts/{contact_id}", json={"name": "Hijacked"}, headers=beta["headers"]
    ).status_code == 404
    assert client.delete(f"/api/contacts/{contact_id}", headers=beta["headers"]).status_code == 404


def test_drafts_and_templates_are_isolated(two_tenants):
    client, alpha, beta = two_tenants

    contact = client.post(
        "/api/contacts",
        json={"email": f"draft-target-{uuid.uuid4().hex[:6]}@example.com"},
        headers=alpha["headers"],
    ).json()

    draft = client.post(
        "/api/drafts/compose",
        json={"contact_id": contact["id"], "subject": "Secret", "body": "Alpha only"},
        headers=alpha["headers"],
    )
    assert draft.status_code == 200, draft.text
    draft_id = draft.json()["id"]

    assert client.get(f"/api/drafts/{draft_id}", headers=beta["headers"]).status_code == 404
    assert client.post(
        f"/api/drafts/{draft_id}/send", headers=beta["headers"]
    ).status_code == 404

    beta_drafts = client.get("/api/drafts", headers=beta["headers"]).json()
    assert all(d["id"] != draft_id for d in beta_drafts)

    template = client.post(
        "/api/templates",
        json={
            "name": "Alpha Template",
            "category": "intro",
            "subject_template": "Hi",
            "body_template": "Body",
        },
        headers=alpha["headers"],
    )
    assert template.status_code == 200, template.text
    template_id = template.json()["id"]

    beta_templates = client.get("/api/templates", headers=beta["headers"]).json()["templates"]
    assert all(t["id"] != template_id for t in beta_templates)
    assert client.delete(
        f"/api/templates/{template_id}", headers=beta["headers"]
    ).status_code == 404


def test_settings_and_smtp_are_per_tenant(two_tenants):
    client, alpha, beta = two_tenants

    saved = client.post(
        "/api/settings",
        json={"business_name": "Alpha Co", "goal": "Alpha goal"},
        headers=alpha["headers"],
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["business_name"] == "Alpha Co"

    beta_settings = client.get("/api/settings", headers=beta["headers"])
    assert beta_settings.status_code == 200
    assert beta_settings.json()["business_name"] != "Alpha Co"

    client.post(
        "/api/smtp/config",
        json={"host": "smtp.alpha.test", "port": 587, "sender": "a@alpha.test"},
        headers=alpha["headers"],
    )
    beta_smtp = client.get("/api/smtp/status", headers=beta["headers"]).json()
    assert beta_smtp["host"] != "smtp.alpha.test"


def test_state_endpoint_is_tenant_scoped(two_tenants):
    client, alpha, beta = two_tenants

    contact = client.post(
        "/api/contacts",
        json={"email": f"state-lead-{uuid.uuid4().hex[:6]}@example.com", "name": "State Lead"},
        headers=alpha["headers"],
    ).json()

    alpha_state = client.get("/api/state", headers=alpha["headers"])
    assert alpha_state.status_code == 200
    assert any(c["id"] == contact["id"] for c in alpha_state.json()["contacts"])

    beta_state = client.get("/api/state", headers=beta["headers"])
    assert beta_state.status_code == 200
    assert all(c["id"] != contact["id"] for c in beta_state.json()["contacts"])


def test_run_all_only_touches_the_callers_contacts(two_tenants):
    client, alpha, beta = two_tenants

    alpha_contact = client.post(
        "/api/contacts",
        json={
            "email": f"runall-alpha-{uuid.uuid4().hex[:6]}@example.com",
            "eligible_to_email": True,
        },
        headers=alpha["headers"],
    ).json()

    response = client.post("/api/queue/run-all", json={}, headers=beta["headers"])
    assert response.status_code in (200, 404)

    beta_drafts = client.get("/api/drafts", headers=beta["headers"]).json()
    assert all(d["contact_id"] != alpha_contact["id"] for d in beta_drafts)


def test_state_analytics_are_computed_and_tenant_scoped(two_tenants):
    client, alpha, beta = two_tenants

    state = client.get("/api/state", headers=alpha["headers"])
    assert state.status_code == 200
    analytics = state.json()["analytics"]

    assert set(analytics) == {
        "sent",
        "failed",
        "pending",
        "replied",
        "auto_replies",
        "followups_due",
        "followups_sent",
        "interested",
        "interested_contacts",
        "reply_types",
        "reply_rate",
        "series",
    }
    assert len(analytics["series"]) == 14
    assert all({"date", "sent", "replied"} <= set(day) for day in analytics["series"])
    assert analytics["reply_rate"] >= 0
    # The series is the last 14 days, so it can never exceed the all-time total.
    assert sum(day["sent"] for day in analytics["series"]) <= analytics["sent"]

    # A second tenant sees the same shape, computed from its own rows only.
    beta_analytics = client.get("/api/state", headers=beta["headers"]).json()["analytics"]
    assert set(beta_analytics) == set(analytics)
    assert sum(day["sent"] for day in beta_analytics["series"]) <= beta_analytics["sent"]
    assert [d["date"] for d in beta_analytics["series"]] == [
        d["date"] for d in analytics["series"]
    ]


def test_every_resource_router_requires_auth_unless_single_user():
    # No lifespan re-entry: the app is already initialized by the session client.
    # This client carries no Authorization header, so every call is anonymous.
    anon = TestClient(app)
    expected = (200,) if settings.SINGLE_USER_MODE else (401, 403)
    protected_paths = [
        ("get", "/api/contacts"),
        ("get", "/api/drafts"),
        ("get", "/api/templates"),
        ("get", "/api/smtp/status"),
        ("get", "/api/settings"),
        ("get", "/api/queue/status"),
        ("get", "/api/inbox"),
        ("get", "/api/tracking"),
        ("get", "/api/verifications"),
        ("get", "/api/agents/status"),
        ("get", "/api/state"),
    ]
    for method, path in protected_paths:
        response = getattr(anon, method)(path)
        assert response.status_code in expected, f"{path} returned {response.status_code}"


def test_refresh_token_returns_a_working_token(two_tenants):
    client, alpha, _beta = two_tenants

    response = client.post("/api/auth/refresh-token", headers=alpha["headers"])
    assert response.status_code == 200, response.text
    new_token = response.json()["access_token"]
    assert new_token

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == alpha["email"]
