"""CSV import collects name and email only.

The address book deliberately stores nothing else, so a CSV column such as
``company`` must not be written -- otherwise an import silently fills fields the
operator never asked for.
"""
import uuid


def _headers(client):
    suffix = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"import-{suffix}@example.org",
            "password": "import-password-123",
            "name": "Import Tester",
            "tenant_name": f"Import Tenant {suffix}",
        },
    )
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_import_keeps_only_name_and_email(client):
    # A fresh tenant: the session tenant accumulates contacts across the suite.
    # A unique local part keeps the address from colliding with an earlier run.
    headers = _headers(client)
    email = f"lead-a-{uuid.uuid4().hex[:8]}@example.com"
    csv = f"email,name,company,role\n{email},Lead A,Acme,CTO\n"
    response = client.post("/api/contacts/import", json={"csv": csv}, headers=headers)
    assert response.status_code == 200, response.text

    state = client.get("/api/state", headers=headers).json()
    contact = next(c for c in state["contacts"] if c["email"] == email)
    assert contact["name"] == "Lead A"
    # None of the extra CSV columns may have been written.
    assert contact["company"] is None
    assert contact["role"] is None


def test_import_updates_name_without_touching_other_fields(client):
    headers = _headers(client)
    email = f"lead-b-{uuid.uuid4().hex[:8]}@example.com"

    created = client.post("/api/contacts", json={"email": email, "name": "Original"}, headers=headers)
    assert created.status_code == 200, created.text

    csv = f"email,name,company\n{email},Renamed,NewCo\n"
    response = client.post("/api/contacts/import", json={"csv": csv}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    # The contact already exists, so the import updates it rather than creating it.
    assert body.get("updated") == 1, body

    state = client.get("/api/state", headers=headers).json()
    contact = next(c for c in state["contacts"] if c["email"] == email)
    assert contact["name"] == "Renamed"
    assert contact["company"] is None