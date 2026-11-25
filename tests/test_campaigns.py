"""Campaigns API contracts: listing, filtering, lifecycle and isolation."""
import uuid

from app.db import Campaign, SessionLocal


def _campaign(client, headers, **extra):
    payload = {"name": f"Campaign {uuid.uuid4().hex[:8]}", "channel": "email"}
    payload.update(extra)
    response = client.post("/api/campaigns", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _list(client, headers):
    response = client.post(
        "/api/lists", json={"name": f"Camp {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_campaign_crud_lifecycle(client):
    headers = dict(client.headers)

    created = _campaign(client, headers, subject="Hello there")
    assert created["status"] == "draft"
    assert created["channel"] == "email"
    assert created["subject"] == "Hello there"
    campaign_id = created["id"]

    fetched = client.get(f"/api/campaigns/{campaign_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == campaign_id

    listed = client.get("/api/campaigns", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == campaign_id for row in listed.json())

    renamed = client.patch(
        f"/api/campaigns/{campaign_id}", json={"name": "Renamed campaign"}, headers=headers
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed campaign"

    deleted = client.delete(f"/api/campaigns/{campaign_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/campaigns/{campaign_id}", headers=headers).status_code == 404


def test_new_campaign_sorts_first_like_brevo(client):
    headers = dict(client.headers)
    first = _campaign(client, headers)
    second = _campaign(client, headers)

    rows = client.get("/api/campaigns?sort=desc", headers=headers).json()
    ids = [row["id"] for row in rows]
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_campaign_filters_by_status_and_search(client):
    headers = dict(client.headers)
    marker = uuid.uuid4().hex[:6]
    campaign = _campaign(client, headers, name=f"Filter {marker}")

    by_search = client.get(f"/api/campaigns?search={marker}", headers=headers).json()
    assert [row["id"] for row in by_search] == [campaign["id"]]

    drafts = client.get("/api/campaigns?status=draft", headers=headers).json()
    assert any(row["id"] == campaign["id"] for row in drafts)

    sent = client.get("/api/campaigns?status=sent", headers=headers).json()
    assert all(row["id"] != campaign["id"] for row in sent)

    assert client.get("/api/campaigns?status=bogus", headers=headers).status_code == 422


def test_campaign_accepts_brevo_camel_case_fields(client):
    headers = dict(client.headers)
    contact_list = _list(client, headers)
    campaign = _campaign(client, headers, listId=contact_list["id"])

    assert campaign["list_id"] == contact_list["id"]
    assert campaign["listId"] == contact_list["id"]
    assert campaign["list_name"] == contact_list["name"]

    # An audience count is captured at creation so the listing can show it.
    assert campaign["total_recipients"] >= 0


def test_campaign_pairing_with_a_foreign_list_is_rejected(client):
    alpha = dict(client.headers)
    alpha_list = _list(client, alpha)

    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"camp-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Beta",
            "tenant_name": f"Camp Beta {suffix}",
        },
    )
    beta = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    assert client.get("/api/campaigns", headers=beta).json() == []
    assert client.post(
        "/api/campaigns",
        json={"name": "Steal", "list_id": alpha_list["id"]},
        headers=beta,
    ).status_code == 404


def test_campaign_duplicate_pause_and_cancel(client):
    headers = dict(client.headers)
    campaign = _campaign(client, headers)

    copy = client.post(
        f"/api/campaigns/{campaign['id']}/duplicate", json={}, headers=headers
    )
    assert copy.status_code == 201, copy.text
    assert copy.json()["status"] == "draft"
    assert copy.json()["id"] != campaign["id"]

    paused = client.post(f"/api/campaigns/{campaign['id']}/pause", json={}, headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    cancelled = client.post(
        f"/api/campaigns/{campaign['id']}/cancel", json={}, headers=headers
    )
    assert cancelled.json()["status"] == "cancelled"

    # A cancelled campaign cannot be sent.
    blocked = client.post(
        "/api/queue/run-all",
        json={"campaign_id": campaign["id"]},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text


def test_campaign_stats_and_summary_shape(client):
    headers = dict(client.headers)
    campaign = _campaign(client, headers)

    stats = client.get(f"/api/campaigns/{campaign['id']}/stats", headers=headers)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    for field in (
        "total_recipients",
        "delivered",
        "opened",
        "clicked",
        "replied",
        "bounced",
        "unsubscribed",
        "open_rate",
        "click_rate",
    ):
        assert field in body["stats"], body

    summary = client.get("/api/campaigns/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body["total"] >= 1
    assert "draft" in summary_body["by_status"]
    assert summary_body["supported_channels"] == ["email"]


def test_non_email_channels_are_refused_at_create(client):
    """Email is the only channel; SMS/WhatsApp are rejected up front."""
    headers = dict(client.headers)
    response = client.post(
        "/api/campaigns",
        json={"name": "SMS campaign", "channel": "sms"},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert "email" in response.json()["detail"].lower()


def test_non_email_channels_are_refused_at_send_time(client):
    """A legacy non-email campaign (created before email-only) is refused at send."""
    headers = dict(client.headers)
    campaign = _campaign(client, headers)
    # Force the channel past create-time validation to simulate a legacy row.
    db = SessionLocal()
    try:
        row = db.query(Campaign).filter(Campaign.id == campaign["id"]).one()
        row.channel = "sms"
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/queue/run-all", json={"campaign_id": campaign["id"]}, headers=headers
    )
    assert response.status_code == 422, response.text
    assert "email" in response.json()["detail"].lower()


def test_invalid_channel_and_status_are_rejected(client):
    headers = dict(client.headers)
    assert client.post(
        "/api/campaigns", json={"name": "Bad", "channel": "pigeon"}, headers=headers
    ).status_code == 422

    campaign = _campaign(client, headers)
    assert client.patch(
        f"/api/campaigns/{campaign['id']}", json={"status": "bogus"}, headers=headers
    ).status_code == 422


def test_campaign_row_is_tenant_scoped_in_the_database(client):
    headers = dict(client.headers)
    campaign = _campaign(client, headers)

    db = SessionLocal()
    try:
        row = db.query(Campaign).filter(Campaign.id == campaign["id"]).one()
        assert row.tenant_id is not None
    finally:
        db.close()
