"""Scheduling control tests: status, autopilot toggle and history."""
import uuid

import pytest


def _fresh_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"sched-{suffix}@example.com",
            "password": "sched-password-123",
            "name": "Sched User",
            "tenant_name": f"Sched Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def test_scheduling_status_reports_jobs_and_flags(client):
    headers = _fresh_headers(client)

    response = client.get("/api/scheduling/status", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert isinstance(body["jobs"], list)
    assert {job["id"] for job in body["jobs"]} == {"inbox_poll", "autopilot"}
    for job in body["jobs"]:
        assert "scheduled" in job
        assert "next_run" in job
    assert isinstance(body["autopilot_enabled"], bool)
    assert isinstance(body["auto_approve_enabled"], bool)


def test_autopilot_toggle_round_trips(client):
    headers = _fresh_headers(client)

    enabled = client.post(
        "/api/scheduling/autopilot", json={"enabled": True}, headers=headers
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["autopilot_enabled"] is True
    assert enabled.json()["auto_approve_enabled"] is True

    status = client.get("/api/scheduling/status", headers=headers).json()
    assert status["autopilot_enabled"] is True
    assert status["auto_approve_enabled"] is True

    disabled = client.post(
        "/api/scheduling/autopilot", json={"enabled": False}, headers=headers
    )
    assert disabled.json()["autopilot_enabled"] is False

    status_after = client.get("/api/scheduling/status", headers=headers).json()
    assert status_after["autopilot_enabled"] is False


def test_autopilot_toggle_does_not_leak_across_tenants(client):
    alpha_headers = _fresh_headers(client)
    beta_headers = _fresh_headers(client)

    # Environments can default autopilot on, so pin beta off first and prove
    # that enabling it for alpha does not flip beta back.
    client.post("/api/scheduling/autopilot", json={"enabled": False}, headers=beta_headers)
    client.post("/api/scheduling/autopilot", json={"enabled": True}, headers=alpha_headers)

    assert client.get(
        "/api/scheduling/status", headers=alpha_headers
    ).json()["autopilot_enabled"] is True
    assert client.get(
        "/api/scheduling/status", headers=beta_headers
    ).json()["autopilot_enabled"] is False


def test_explicit_auto_approve_is_respected(client):
    headers = _fresh_headers(client)

    response = client.post(
        "/api/scheduling/autopilot",
        json={"enabled": True, "auto_approve": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["autopilot_enabled"] is True
    assert response.json()["auto_approve_enabled"] is False


def test_history_returns_scheduler_entries(client):
    headers = _fresh_headers(client)

    client.post("/api/scheduling/autopilot", json={"enabled": True}, headers=headers)
    client.post("/api/scheduling/autopilot", json={"enabled": False}, headers=headers)

    response = client.get("/api/scheduling/history", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert isinstance(body["history"], list)
    assert body["generated_at"]
    assert any(entry["type"] == "autopilot" for entry in body["history"])

    limited = client.get("/api/scheduling/history?limit=1", headers=headers).json()
    assert len(limited["history"]) <= 1


def test_history_is_tenant_scoped(client):
    alpha_headers = _fresh_headers(client)
    beta_headers = _fresh_headers(client)

    client.post("/api/scheduling/autopilot", json={"enabled": True}, headers=alpha_headers)

    alpha_messages = {e["message"] for e in client.get("/api/scheduling/history", headers=alpha_headers).json()["history"]}
    beta_messages = {e["message"] for e in client.get("/api/scheduling/history", headers=beta_headers).json()["history"]}

    assert alpha_messages
    assert alpha_messages.isdisjoint(beta_messages)
