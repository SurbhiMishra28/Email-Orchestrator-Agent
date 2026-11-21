"""Exact request shapes the Contacts dashboard sends."""
import uuid


def _new_contact(client, **extra):
    payload = {
        "email": f"ui-{uuid.uuid4().hex[:8]}@example.com",
        "name": "UI Contact",
        "company": "UI Co",
        "role": "CTO",
        "industry": "Tech",
        "notes": "n",
        "eligible_to_email": True,
    }
    payload.update(extra)
    r = client.post("/api/contacts", json=payload, headers=dict(client.headers))
    assert r.status_code == 200, r.text
    return r.json()


def test_create_contact_returns_all_columns_the_table_renders(client):
    c = _new_contact(client)
    for field in ("id", "email", "name", "company", "eligible_to_email"):
        assert field in c, f"table needs {field}: {c}"


def test_bulk_delete_route_is_not_shadowed_by_id_route(client):
    a = _new_contact(client)
    b = _new_contact(client)
    r = client.request(
        "DELETE",
        "/api/contacts/bulk",
        json={"contact_ids": [a["id"], b["id"]]},
        headers=dict(client.headers),
    )
    assert r.status_code in (200, 204), r.text

    remaining = client.get("/api/contacts?limit=1000", headers=dict(client.headers)).json()
    ids = {x["id"] for x in remaining}
    assert a["id"] not in ids
    assert b["id"] not in ids


def test_eligibility_toggle_round_trip(client):
    c = _new_contact(client, eligible_to_email=False)
    h = dict(client.headers)
    on = client.post(f"/api/contacts/{c['id']}/eligibility", json={"eligible_to_email": True}, headers=h)
    assert on.status_code == 200, on.text
    assert on.json()["eligible_to_email"] is True

    off = client.post(f"/api/contacts/{c['id']}/eligibility", json={"eligible_to_email": False}, headers=h)
    assert off.status_code == 200, off.text
    assert off.json()["eligible_to_email"] is False


def test_contact_tags_flow(client):
    c = _new_contact(client)
    h = dict(client.headers)

    added = client.post(f"/api/contacts/{c['id']}/tags?tag=vip", headers=h)
    assert added.status_code in (200, 201), added.text
    assert "vip" in added.json()["tags"]

    tags = client.get("/api/contacts/tags", headers=h)
    assert tags.status_code == 200
    assert "vip" in tags.json()["tags"]

    removed = client.delete(f"/api/contacts/{c['id']}/tags/vip", headers=h)
    assert removed.status_code in (200, 204), removed.text
    assert "vip" not in removed.json()["tags"]


def test_reimport_updates_instead_of_duplicating(client):
    """Re-importing is an upsert: it must report updates, not new imports."""
    h = dict(client.headers)
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    csv = f"email,name\n{email},First\n"
    first = client.post("/api/contacts/import", json={"csv": csv}, headers=h)
    assert first.status_code == 200, first.text
    assert first.json()["imported"] == 1
    assert first.json().get("updated", 0) == 0

    second = client.post("/api/contacts/import", json={"csv": csv}, headers=h)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["imported"] == 0, body
    assert body["updated"] == 1, body

    matches = [x for x in client.get("/api/contacts?limit=1000", headers=h).json() if x["email"] == email]
    assert len(matches) == 1, "re-import must not create a duplicate"
