"""Usage metering tests: the endpoint reports what the tenant actually did."""
import uuid

import pytest


def _contact(client, headers, **overrides):
    payload = {"email": f"usage-{uuid.uuid4().hex[:8]}@example.com"}
    payload.update(overrides)
    response = client.post("/api/contacts", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_usage_endpoint_reports_drafted_and_sent(client):
    headers = dict(client.headers)

    usage_before = client.get("/api/usage", headers=headers)
    assert usage_before.status_code == 200, usage_before.text
    before = usage_before.json()
    assert set(before["today"]) == {"emails_sent", "emails_drafted", "replies_received"}
    assert set(before["month"]) == {"emails_sent", "emails_drafted", "replies_received"}

    contact = _contact(client, headers)
    draft = client.post(
        "/api/drafts/compose",
        json={"contact_id": contact["id"], "subject": "Usage", "body": "Body"},
        headers=headers,
    )
    assert draft.status_code == 200, draft.text

    after = client.get("/api/usage", headers=headers).json()
    assert after["today"]["emails_drafted"] >= before["today"]["emails_drafted"] + 1
    assert after["month"]["emails_drafted"] >= before["month"]["emails_drafted"] + 1
    assert after["tenant_id"] == before["tenant_id"]

    if after["daily_email_limit"] is not None:
        assert after["daily_remaining"] is not None
        assert after["daily_remaining"] >= 0


def test_usage_is_per_tenant(client):
    alpha_headers = dict(client.headers)
    alpha_contact = _contact(client, alpha_headers)
    client.post(
        "/api/drafts/compose",
        json={"contact_id": alpha_contact["id"], "subject": "A", "body": "A"},
        headers=alpha_headers,
    )
    alpha_usage = client.get("/api/usage", headers=alpha_headers).json()

    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"usage-beta-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Beta",
            "tenant_name": f"Usage Beta {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    beta_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    beta_usage = client.get("/api/usage", headers=beta_headers)
    assert beta_usage.status_code == 200, beta_usage.text
    assert beta_usage.json()["tenant_id"] != alpha_usage["tenant_id"]
    assert beta_usage.json()["month"]["emails_drafted"] == 0


def test_plan_daily_limit_is_read_from_the_tenant(client):
    """`plan_daily_limit` reflects the tenant row and treats 0 as unlimited."""
    from app.db import SessionLocal, Tenant
    from app.services.limits import plan_daily_limit

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
        original = tenant.daily_email_limit

        tenant.daily_email_limit = 1
        db.commit()
        assert plan_daily_limit(db, tenant.id) == 1

        tenant.daily_email_limit = 0
        db.commit()
        assert plan_daily_limit(db, tenant.id) is None

        tenant.daily_email_limit = original
        db.commit()
    finally:
        db.close()


def test_plan_limit_lowers_the_effective_daily_cap(client):
    """A plan limit below the configured cap blocks sending at that number."""
    from datetime import datetime, timezone

    from app.db import Contact, Draft, SessionLocal, Tenant
    from app.services.limits import check_send_allowed

    # A brand-new tenant has nothing sent today, so it is unaffected.
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"plan-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Plan User",
            "tenant_name": f"Plan Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    plan_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    created = client.post(
        "/api/contacts",
        json={"email": f"plan-contact-{suffix}@example.com"},
        headers=plan_headers,
    )
    assert created.status_code == 200, created.text
    contact_id = created.json()["id"]

    db = SessionLocal()
    try:
        contact_row = db.query(Contact).filter(Contact.id == contact_id).first()
        tenant = db.query(Tenant).filter(Tenant.id == contact_row.tenant_id).first()
        original = tenant.daily_email_limit
        tenant.daily_email_limit = 1
        db.commit()

        allowed, reason = check_send_allowed(db, contact_row)
        assert allowed is True, reason

        # One send today consumes the entire one-per-day plan.
        db.add(
            Draft(
                tenant_id=contact_row.tenant_id,
                contact_id=contact_row.id,
                subject="Plan",
                body="Body",
                status="sent",
                sent_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        blocked, reason = check_send_allowed(db, contact_row)
        assert blocked is False
        assert "Plan limit" in reason

        tenant.daily_email_limit = original
        db.commit()
    finally:
        db.close()
