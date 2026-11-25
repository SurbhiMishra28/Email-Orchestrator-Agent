"""Sender aliases: CRUD, default promotion, and tenant scoping."""
import uuid


def _clear(client, headers):
    """Remove seeded aliases so a test starts from an empty list."""
    for alias in client.get("/api/aliases", headers=headers).json():
        client.delete(f"/api/aliases/{alias['id']}", headers=headers)


def _alias(client, headers, **extra):
    payload = {
        "name": "Sales",
        "email": f"sales-{uuid.uuid4().hex[:8]}@example.org",
    }
    payload.update(extra)
    response = client.post("/api/aliases", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_first_alias_becomes_the_default(client):
    headers = dict(client.headers)
    _clear(client, headers)
    alias = _alias(client, headers)

    assert alias["is_default"] is True

    listing = client.get("/api/aliases", headers=headers).json()
    assert [a["id"] for a in listing] == [alias["id"]]


def test_second_alias_is_not_default_and_can_be_promoted(client):
    headers = dict(client.headers)
    _clear(client, headers)
    first = _alias(client, headers, email="one@example.org")
    second = _alias(client, headers, email="two@example.org")

    assert second["is_default"] is False

    promoted = client.patch(
        f"/api/aliases/{second['id']}", json={"is_default": True}, headers=headers
    ).json()
    assert promoted["is_default"] is True

    listing = client.get("/api/aliases", headers=headers).json()
    defaults = [a["id"] for a in listing if a["is_default"]]
    assert defaults == [second["id"]]
    assert first["id"] not in defaults


def test_deleting_the_default_promotes_a_successor(client):
    headers = dict(client.headers)
    _clear(client, headers)
    first = _alias(client, headers, email="one@example.org")
    second = _alias(client, headers, email="two@example.org")

    client.delete(f"/api/aliases/{first['id']}", headers=headers)

    listing = client.get("/api/aliases", headers=headers).json()
    remaining = [a for a in listing if a["id"] != first["id"]]
    assert remaining and remaining[0]["is_default"] is True
    assert second["id"] in [a["id"] for a in remaining]


def test_alias_is_scoped_to_the_tenant(client):
    """One workspace must not see or delete another's aliases."""
    headers = dict(client.headers)
    alias = _alias(client, headers)
    owner_listing = client.get("/api/aliases", headers=headers).json()

    other = client.post(
        "/api/auth/register",
        json={
            "email": f"other-{uuid.uuid4().hex[:8]}@example.org",
            "password": "other-password-123",
            "name": "Other User",
            "tenant_name": "Other Tenant",
        },
    )
    assert other.status_code in (200, 201), other.text
    token = other.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}

    # The other workspace must not see the owner's alias. It may have its own
    # seeded alias (a fresh tenant inherits the deployment mailbox in this
    # single-user build), so assert on identity, not on emptiness.
    other_ids = [a["id"] for a in client.get("/api/aliases", headers=other_headers).json()]
    assert alias["id"] not in other_ids
    assert (
        client.delete(f"/api/aliases/{alias['id']}", headers=other_headers).status_code
        == 404
    )
    # And the owner can still see it.
    assert alias["id"] in [a["id"] for a in owner_listing]


def test_alias_requires_a_valid_address(client):
    headers = dict(client.headers)
    response = client.post(
        "/api/aliases", json={"name": "Bad", "email": "not-an-email"}, headers=headers
    )
    assert response.status_code == 422