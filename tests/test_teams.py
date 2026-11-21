"""Team management tests: invite, role changes, removal and admin guards."""
import uuid

import pytest


def _member_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"team-{suffix}@example.com",
            "password": "team-password-123",
            "name": "Team Admin",
            "tenant_name": f"Team Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def test_tenant_summary_is_returned(client):
    headers = _member_headers(client)

    response = client.get("/api/tenants", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["member_count"] >= 1
    assert body["daily_email_limit"] is not None
    assert {"id", "name", "plan", "daily_email_limit", "member_count"} <= set(body)


def test_registering_admin_appears_as_a_member(client):
    headers = _member_headers(client)

    members = client.get("/api/tenants/members", headers=headers)
    assert members.status_code == 200, members.text
    rows = members.json()
    assert len(rows) >= 1
    assert any(row["role"] == "admin" for row in rows)


def test_invite_creates_a_usable_member(client):
    headers = _member_headers(client)
    email = f"invited-{uuid.uuid4().hex[:8]}@example.com"

    invited = client.post(
        "/api/tenants/members",
        json={"email": email, "name": "Invited Person", "role": "member"},
        headers=headers,
    )
    assert invited.status_code == 201, invited.text
    body = invited.json()
    assert body["email"] == email
    assert body["role"] == "member"
    assert body["temporary_password"]

    emailed = [row for row in client.get("/api/tenants/members", headers=headers).json()
               if row["email"] == email]
    assert len(emailed) == 1

    # The generated password must actually work for sign-in.
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": body["temporary_password"]},
    )
    assert login.status_code == 200, login.text


def test_duplicate_invite_is_rejected(client):
    headers = _member_headers(client)
    email = f"dupe-{uuid.uuid4().hex[:8]}@example.com"

    assert client.post(
        "/api/tenants/members", json={"email": email, "role": "member"}, headers=headers
    ).status_code == 201

    duplicate = client.post(
        "/api/tenants/members", json={"email": email, "role": "member"}, headers=headers
    )
    assert duplicate.status_code == 409, duplicate.text


def test_invalid_role_is_rejected(client):
    headers = _member_headers(client)
    response = client.post(
        "/api/tenants/members",
        json={"email": f"role-{uuid.uuid4().hex[:8]}@example.com", "role": "owner"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_role_can_be_promoted_and_demoted(client):
    headers = _member_headers(client)
    email = f"promote-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post(
        "/api/tenants/members",
        json={"email": email, "role": "member"},
        headers=headers,
    ).json()

    promoted = client.patch(
        f"/api/tenants/members/{invited['id']}",
        json={"role": "admin"},
        headers=headers,
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "admin"

    demoted = client.patch(
        f"/api/tenants/members/{invited['id']}",
        json={"role": "member"},
        headers=headers,
    )
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["role"] == "member"


def test_member_can_be_removed(client):
    headers = _member_headers(client)
    email = f"remove-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post(
        "/api/tenants/members",
        json={"email": email, "role": "member"},
        headers=headers,
    ).json()

    removed = client.delete(f"/api/tenants/members/{invited['id']}", headers=headers)
    assert removed.status_code == 200, removed.text

    remaining = [row["id"] for row in client.get("/api/tenants/members", headers=headers).json()]
    assert invited["id"] not in remaining


def test_last_admin_cannot_be_demoted_or_removed(client):
    headers = _member_headers(client)
    admins = [row for row in client.get("/api/tenants/members", headers=headers).json()
              if row["role"] == "admin"]
    assert len(admins) == 1
    sole_admin = admins[0]

    demote = client.patch(
        f"/api/tenants/members/{sole_admin['id']}",
        json={"role": "member"},
        headers=headers,
    )
    assert demote.status_code == 409, demote.text

    remove = client.delete(f"/api/tenants/members/{sole_admin['id']}", headers=headers)
    assert remove.status_code == 409, remove.text


def test_members_are_tenant_isolated(client):
    alpha_headers = _member_headers(client)
    beta_headers = _member_headers(client)

    alpha_member = client.post(
        "/api/tenants/members",
        json={"email": f"iso-{uuid.uuid4().hex[:8]}@example.com", "role": "member"},
        headers=alpha_headers,
    ).json()

    beta_ids = {row["id"] for row in client.get("/api/tenants/members", headers=beta_headers).json()}
    assert alpha_member["id"] not in beta_ids
    assert client.patch(
        f"/api/tenants/members/{alpha_member['id']}",
        json={"role": "admin"},
        headers=beta_headers,
    ).status_code == 404
    assert client.delete(
        f"/api/tenants/members/{alpha_member['id']}", headers=beta_headers
    ).status_code == 404


def test_non_admin_cannot_manage_members(client):
    admin_headers = _member_headers(client)
    email = f"nonadmin-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post(
        "/api/tenants/members",
        json={"email": email, "role": "member"},
        headers=admin_headers,
    ).json()

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": invited["temporary_password"]},
    )
    assert login.status_code == 200, login.text
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/tenants", headers=member_headers).status_code == 403
    assert client.get("/api/tenants/members", headers=member_headers).status_code == 403
    assert client.post(
        "/api/tenants/members",
        json={"email": f"blocked-{uuid.uuid4().hex[:8]}@example.com"},
        headers=member_headers,
    ).status_code == 403
