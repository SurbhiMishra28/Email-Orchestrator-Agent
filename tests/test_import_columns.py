"""CSV import collects name and email only.

The address book deliberately stores nothing else, so a CSV column such as
``company`` must not be written -- otherwise an import silently fills fields the
operator never asked for.
"""
import uuid


def _headers(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"import-{uuid.uuid4().hex[:8]}@example.org",
            "password": "import-password-123",
            "name": "Import Tester",
            "tenant_name": "Import Tenant",
        },
    )
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_import_keeps_only_name_and_email(client):
    headers = dict(client.headers)
    csv = (
        "email,name,company,role\n"
        "lead-a@skorainfotech.com,Lead A,Acme,CTO\n"
    )
    response = client.post("/api/contacts/import", json={"csv": csv}, headers=headers)
    assert response.status_code == 200, response.text

    state = client.get("/api/state", headers=headers).json()
    contact = next(c for c in state["contacts"] if c["email"] == "lead-a@skorainfotech.com")
    assert contact["name"] == "Lead A"
    # None of the extra CSV columns may have been written.
    assert contact["company"] is None
    assert contact["role"] is None


def test_import_updates_name_without_touching_other_fields(client):
    headers = dict(client.headers)
    email = f"lead-b-{uuid.uuid4().hex[:6]}@skorainfotech.com"

    client.post("/api/contacts", json={"email": email, "name": "Original"}, headers=headers)
    csv = f"email,name,company\n{email},Renamed,NewCo\n"
    response = client.post("/api/contacts/import", json={"csv": csv}, headers=headers)
    assert response.status_code == 200, response.text

    state = client.get("/api/state", headers=headers).json()
    contact = next(c for c in state["contacts"] if c["email"] == email)
    assert contact["name"] == "Renamed"
    assert contact["company"] is None