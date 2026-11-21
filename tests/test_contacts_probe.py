import uuid


def _contact(client, headers, **extra):
    payload = {"email": f"probe-{uuid.uuid4().hex[:8]}@example.com", "name": "Probe"}
    payload.update(extra)
    r = client.post("/api/contacts", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_contacts_crud_probe(client):
    h = dict(client.headers)
    c = _contact(client, h)
    cid = c["id"]

    assert client.get(f"/api/contacts/{cid}", headers=h).status_code == 200

    upd = client.patch(f"/api/contacts/{cid}", json={"name": "Renamed"}, headers=h)
    assert upd.status_code == 200, upd.text
    assert upd.json()["name"] == "Renamed"

    el = client.post(
        f"/api/contacts/{cid}/eligibility",
        json={"eligible_to_email": True},
        headers=h,
    )
    assert el.status_code == 200, el.text

    lst = client.post("/api/lists", json={"name": "Probe list"}, headers=h)
    assert lst.status_code in (200, 201), lst.text
    lid = lst.json()["id"]

    add = client.post(
        f"/api/lists/{lid}/contacts",
        json={"contact_ids": [cid]},
        headers=h,
    )
    assert add.status_code == 200, add.text

    members = client.get(f"/api/lists/{lid}/contacts", headers=h)
    assert members.status_code == 200
    assert any(m["id"] == cid for m in members.json())

    filtered = client.get(f"/api/contacts?list_id={lid}", headers=h)
    assert filtered.status_code == 200
    assert any(x["id"] == cid for x in filtered.json())

    rm = client.delete(f"/api/lists/{lid}/contacts/{cid}", headers=h)
    assert rm.status_code == 200, rm.text

    dl = client.delete(f"/api/contacts/{cid}", headers=h)
    assert dl.status_code == 200, dl.text
    assert client.get(f"/api/contacts/{cid}", headers=h).status_code == 404


def test_contacts_import_probe(client):
    h = dict(client.headers)
    email = f"csv-{uuid.uuid4().hex[:8]}@example.com"
    csv = f"email,name,company\n{email},Csv Person,Acme\n"
    r = client.post("/api/contacts/import", json={"csv": csv}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("imported", 0) >= 1, body

    found = client.get("/api/contacts?limit=1000", headers=h).json()
    assert any(x["email"] == email for x in found)
