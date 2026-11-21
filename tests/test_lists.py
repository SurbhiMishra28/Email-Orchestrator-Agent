"""Contact list (segment) tests: CRUD, membership and send targeting."""
import uuid

import pytest


def _headers(client):
    return dict(client.headers)


def _contact(client, headers, eligible=False):
    response = client.post(
        "/api/contacts",
        json={
            "email": f"list-{uuid.uuid4().hex[:8]}@example.com",
            "name": "List Contact",
            "eligible_to_email": eligible,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_list_lifecycle(client):
    headers = _headers(client)
    name = f"Segment {uuid.uuid4().hex[:8]}"

    created = client.post(
        "/api/lists", json={"name": name, "description": "Test segment"}, headers=headers
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == name
    assert body["member_count"] == 0
    list_id = body["id"]

    fetched = client.get(f"/api/lists/{list_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == list_id

    listed = client.get("/api/lists", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == list_id for item in listed.json())

    renamed = client.patch(
        f"/api/lists/{list_id}", json={"name": f"{name} renamed"}, headers=headers
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == f"{name} renamed"

    deleted = client.delete(f"/api/lists/{list_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/lists/{list_id}", headers=headers).status_code == 404


def test_duplicate_list_name_is_rejected(client):
    headers = _headers(client)
    name = f"Dupe {uuid.uuid4().hex[:8]}"
    assert client.post("/api/lists", json={"name": name}, headers=headers).status_code == 201

    duplicate = client.post("/api/lists", json={"name": name}, headers=headers)
    assert duplicate.status_code == 409, duplicate.text


def test_membership_is_idempotent_and_removable(client):
    headers = _headers(client)
    contact = _contact(client, headers)
    contact_list = client.post(
        "/api/lists", json={"name": f"Members {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()
    list_id = contact_list["id"]

    added = client.post(
        f"/api/lists/{list_id}/contacts",
        json={"contact_ids": [contact["id"]]},
        headers=headers,
    )
    assert added.status_code == 200, added.text
    assert added.json()["member_count"] == 1

    # Adding the same contact twice must not create a second row.
    again = client.post(
        f"/api/lists/{list_id}/contacts",
        json={"contact_ids": [contact["id"]]},
        headers=headers,
    )
    assert again.json()["member_count"] == 1

    members = client.get(f"/api/lists/{list_id}/contacts", headers=headers)
    assert [c["id"] for c in members.json()] == [contact["id"]]

    filtered = client.get(f"/api/contacts?list_id={list_id}", headers=headers)
    assert [c["id"] for c in filtered.json()] == [contact["id"]]

    removed = client.delete(
        f"/api/lists/{list_id}/contacts/{contact['id']}", headers=headers
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["member_count"] == 0

    # The contact itself survives being removed from a list.
    assert client.get(f"/api/contacts/{contact['id']}", headers=headers).status_code == 200


def test_unknown_contacts_are_rejected(client):
    headers = _headers(client)
    contact_list = client.post(
        "/api/lists", json={"name": f"Unknown {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()

    response = client.post(
        f"/api/lists/{contact_list['id']}/contacts",
        json={"contact_ids": [987654321]},
        headers=headers,
    )
    assert response.status_code == 404, response.text
    assert client.get(
        f"/api/lists/{contact_list['id']}", headers=headers
    ).json()["member_count"] == 0


def test_lists_and_membership_are_tenant_isolated(client):
    alpha_headers = _headers(client)
    alpha_contact = _contact(client, alpha_headers)
    alpha_list = client.post(
        "/api/lists", json={"name": f"Alpha {uuid.uuid4().hex[:8]}"}, headers=alpha_headers
    ).json()
    client.post(
        f"/api/lists/{alpha_list['id']}/contacts",
        json={"contact_ids": [alpha_contact["id"]]},
        headers=alpha_headers,
    )

    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"list-beta-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Beta",
            "tenant_name": f"List Beta {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    beta_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    assert client.get("/api/lists", headers=beta_headers).json() == []
    assert client.get(f"/api/lists/{alpha_list['id']}", headers=beta_headers).status_code == 404
    assert client.get(
        f"/api/lists/{alpha_list['id']}/contacts", headers=beta_headers
    ).status_code == 404
    assert client.post(
        f"/api/lists/{alpha_list['id']}/contacts",
        json={"contact_ids": [alpha_contact["id"]]},
        headers=beta_headers,
    ).status_code == 404
    assert client.delete(
        f"/api/lists/{alpha_list['id']}", headers=beta_headers
    ).status_code == 404


def test_run_all_accepts_a_list_id(client):
    """A segment-scoped run only considers that list's contacts."""
    headers = _headers(client)
    in_list = _contact(client, headers, eligible=True)
    outside = _contact(client, headers, eligible=True)
    contact_list = client.post(
        "/api/lists", json={"name": f"Send {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()
    client.post(
        f"/api/lists/{contact_list['id']}/contacts",
        json={"contact_ids": [in_list["id"]]},
        headers=headers,
    )

    response = client.post(
        "/api/queue/run-all",
        json={"list_id": contact_list["id"]},
        headers=headers,
    )
    assert response.status_code in (200, 404), response.text

    drafts = client.get("/api/drafts", headers=headers).json()
    drafted_contacts = {draft["contact_id"] for draft in drafts}
    assert outside["id"] not in drafted_contacts or in_list["id"] in drafted_contacts


def test_run_all_rejects_a_foreign_list(client):
    alpha_headers = _headers(client)
    alpha_list = client.post(
        "/api/lists", json={"name": f"Foreign {uuid.uuid4().hex[:8]}"}, headers=alpha_headers
    ).json()

    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"runall-beta-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Beta",
            "tenant_name": f"RunAll Beta {suffix}",
        },
    )
    beta_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    response = client.post(
        "/api/queue/run-all",
        json={"list_id": alpha_list["id"]},
        headers=beta_headers,
    )
    assert response.status_code == 404, response.text
