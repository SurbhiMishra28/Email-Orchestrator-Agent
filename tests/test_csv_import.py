"""CSV import must accept the files real exports produce.

The previous parser read the literal header ``email`` and nothing else, so a
Brevo export (``Email,First Name,Last Name``), an Excel file with a UTF-8 BOM, or
a semicolon-delimited file imported zero rows and said nothing about it.
"""
import uuid

import pytest

from app.services.csv_import import CsvImportError, parse_contacts_csv, split_tags


def _headers(client):
    suffix = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"csv-{suffix}@example.org",
            "password": "csv-password-123",
            "name": "CSV Tester",
            "tenant_name": f"CSV Tenant {suffix}",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_brevo_export_headers_are_understood():
    csv = "Email,First Name,Last Name,Company,Phone\nada@example.com,Ada,Lovelace,Acme,+15550100\n"
    rows, errors = parse_contacts_csv(csv)
    assert errors == []
    assert rows[0]["email"] == "ada@example.com"
    assert rows[0]["name"] == "Ada Lovelace"
    assert rows[0]["company"] == "Acme"


def test_bom_and_upper_case_header_are_stripped():
    csv = "\ufeffEMAIL,NAME\nbob@example.com,Bob\n"
    rows, errors = parse_contacts_csv(csv)
    assert errors == []
    assert rows[0]["email"] == "bob@example.com"


def test_semicolon_delimiter_is_detected():
    csv = "\ufeffEMAIL;NOM;PRENOM\ncarol@example.com;Doe;Carol\n"
    rows, _ = parse_contacts_csv(csv)
    assert rows[0]["email"] == "carol@example.com"
    assert rows[0]["name"] == "Carol Doe"


def test_missing_email_column_is_an_error_not_an_empty_import():
    with pytest.raises(CsvImportError):
        parse_contacts_csv("name,company\nAcme,Acme Inc\n")


def test_empty_csv_is_an_error():
    with pytest.raises(CsvImportError):
        parse_contacts_csv("   ")


def test_tags_split_on_any_separator():
    assert split_tags("vip;lead") == ["vip", "lead"]
    assert split_tags("vip|lead") == ["vip", "lead"]
    assert split_tags("vip, lead, vip") == ["vip", "lead"]
    assert split_tags("") == []


def test_list_import_accepts_brevo_csv_and_makes_contacts_mailable(client):
    headers = _headers(client)
    contact_list = client.post(
        "/api/lists", json={"name": f"Import {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()

    email = f"brevo-{uuid.uuid4().hex[:8]}@example.com"
    csv = f"\ufeffEmail,First Name,Last Name\r\n{email},Grace,Hopper\r\n"
    response = client.post(
        f"/api/lists/{contact_list['id']}/import", json={"csv": csv}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["added_to_list"] == 1
    # The list row must not read back as an empty audience.
    assert body["list"]["member_count"] == 1

    contacts = client.get("/api/contacts", headers=headers).json()
    imported = next(item for item in contacts if item["email"] == email)
    assert imported["name"] == "Grace Hopper"
    assert imported["eligible_to_email"] is True


def test_list_import_rejects_a_file_without_an_email_column(client):
    headers = _headers(client)
    contact_list = client.post(
        "/api/lists", json={"name": f"Bad {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()
    response = client.post(
        f"/api/lists/{contact_list['id']}/import",
        json={"csv": "name,company\nAcme,Acme Inc\n"},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert "email" in response.json()["detail"].lower()
