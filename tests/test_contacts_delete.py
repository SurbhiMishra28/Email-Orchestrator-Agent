"""Contact deletion tests: delete-all, bulk cleanup and tenant scoping.

Every test works inside a throwaway tenant so the session-scoped fixture
tenant keeps its data for the rest of the suite.
"""
import uuid


def _new_tenant_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"delete-{suffix}@example.com",
            "password": "tenant-password-123",
            "name": "Delete Tester",
            "tenant_name": f"Delete Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def _contact(client, headers):
    response = client.post(
        "/api/contacts",
        json={"email": f"delete-{uuid.uuid4().hex[:8]}@example.com", "name": "Delete Contact"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _draft(client, headers, contact_id):
    response = client.post(
        "/api/drafts/compose",
        json={"contact_id": contact_id, "subject": "Hello", "body": "Body"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _list_with(client, headers, contact_ids):
    created = client.post(
        "/api/lists", json={"name": f"Delete {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert created.status_code == 201, created.text
    list_id = created.json()["id"]
    added = client.post(
        f"/api/lists/{list_id}/contacts",
        json={"contact_ids": contact_ids},
        headers=headers,
    )
    assert added.status_code == 200, added.text
    assert added.json()["member_count"] == len(contact_ids)
    return list_id


def test_delete_all_contacts_removes_dependent_rows(client):
    headers = _new_tenant_headers(client)
    first = _contact(client, headers)
    second = _contact(client, headers)
    _draft(client, headers, first["id"])
    _draft(client, headers, second["id"])
    list_id = _list_with(client, headers, [first["id"], second["id"]])

    response = client.delete("/api/contacts/all?confirm=true", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_deleted"] == 2
    assert body["drafts_removed"] == 2
    assert body["events_removed"] == 0

    assert client.get("/api/contacts", headers=headers).json() == []
    assert client.get("/api/drafts", headers=headers).json() == []

    # The list survives, but its membership rows are gone.
    listed = client.get(f"/api/lists/{list_id}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["member_count"] == 0


def test_delete_all_on_empty_tenant_is_a_noop(client):
    headers = _new_tenant_headers(client)

    response = client.delete("/api/contacts/all?confirm=true", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "message": "No contacts to delete",
        "total_deleted": 0,
        "drafts_removed": 0,
        "events_removed": 0,
    }


def test_delete_all_is_tenant_scoped(client):
    alpha_headers = _new_tenant_headers(client)
    alpha_contact = _contact(client, alpha_headers)

    beta_headers = _new_tenant_headers(client)
    beta_contact = _contact(client, beta_headers)

    assert client.delete("/api/contacts/all?confirm=true", headers=beta_headers).status_code == 200
    assert client.get("/api/contacts", headers=beta_headers).json() == []

    # Alpha's contacts are untouched by beta's purge.
    assert client.get(
        f"/api/contacts/{alpha_contact['id']}", headers=alpha_headers
    ).status_code == 200
    assert client.get(f"/api/contacts/{beta_contact['id']}", headers=alpha_headers).status_code == 404


def test_delete_all_requires_confirmation(client):
    headers = _new_tenant_headers(client)
    contact = _contact(client, headers)

    refused = client.delete("/api/contacts/all", headers=headers)
    assert refused.status_code == 400, refused.text
    assert "confirm=true" in refused.json()["detail"]

    # Nothing was touched by the refused call.
    assert client.get(
        f"/api/contacts/{contact['id']}", headers=headers
    ).status_code == 200


def test_bulk_delete_clears_list_membership(client):
    headers = _new_tenant_headers(client)
    kept = _contact(client, headers)
    doomed = _contact(client, headers)
    list_id = _list_with(client, headers, [kept["id"], doomed["id"]])

    response = client.request(
        "DELETE",
        "/api/contacts/bulk",
        json={"contact_ids": [doomed["id"]]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_deleted"] == 1

    assert client.get(f"/api/contacts/{doomed['id']}", headers=headers).status_code == 404
    members = client.get(f"/api/lists/{list_id}/contacts", headers=headers).json()
    assert [c["id"] for c in members] == [kept["id"]]


def test_bulk_delete_rejects_foreign_contacts(client):
    alpha_headers = _new_tenant_headers(client)
    alpha_contact = _contact(client, alpha_headers)

    beta_headers = _new_tenant_headers(client)
    response = client.request(
        "DELETE",
        "/api/contacts/bulk",
        json={"contact_ids": [alpha_contact["id"]]},
        headers=beta_headers,
    )
    assert response.status_code == 404, response.text
    assert client.get(
        f"/api/contacts/{alpha_contact['id']}", headers=alpha_headers
    ).status_code == 200

