"""Brevo-style campaign audiences, A/B configuration and analytics."""
import uuid


def _headers(client):
    suffix = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"camp-{suffix}@example.org",
            "password": "camp-password-123",
            "name": "Campaign Tester",
            "tenant_name": f"Campaign Tenant {suffix}",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _list_with_contacts(client, headers, count):
    contact_list = client.post(
        "/api/lists", json={"name": f"Aud {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()
    emails = [f"a-{uuid.uuid4().hex[:8]}@example.com" for _ in range(count)]
    csv = "email,name\n" + "".join(f"{email},Person\n" for email in emails)
    imported = client.post(
        f"/api/lists/{contact_list['id']}/import", json={"csv": csv}, headers=headers
    )
    assert imported.status_code == 200, imported.text
    return contact_list, emails


def test_campaign_targets_several_lists(client):
    headers = _headers(client)
    first, _ = _list_with_contacts(client, headers, 2)
    second, _ = _list_with_contacts(client, headers, 3)

    created = client.post(
        "/api/campaigns",
        json={"name": "Multi", "list_ids": [first["id"], second["id"]]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["total_recipients"] == 5
    assert sorted(body["list_ids"]) == sorted([first["id"], second["id"]])
    assert len(body["list_names"]) == 2


def test_audience_preview_counts_overlap_once(client):
    headers = _headers(client)
    first, emails = _list_with_contacts(client, headers, 2)
    second = client.post(
        "/api/lists", json={"name": f"Dup {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()
    # Put one of the first list's contacts into the second list as well.
    contacts = client.get("/api/contacts", headers=headers).json()
    shared = next(item for item in contacts if item["email"] == emails[0])
    client.post(
        f"/api/lists/{second['id']}/contacts",
        json={"contact_ids": [shared["id"]]},
        headers=headers,
    )

    preview = client.post(
        "/api/campaigns/audience/preview",
        json={"list_ids": [first["id"], second["id"]]},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    # Two unique contacts in total, not three memberships.
    assert body["total_recipients"] == 2
    assert body["overlap"] == 1


def test_exclusion_list_is_subtracted(client):
    headers = _headers(client)
    included, emails = _list_with_contacts(client, headers, 3)
    excluded = client.post(
        "/api/lists", json={"name": f"Excl {uuid.uuid4().hex[:8]}"}, headers=headers
    ).json()
    contacts = client.get("/api/contacts", headers=headers).json()
    target = next(item for item in contacts if item["email"] == emails[1])
    client.post(
        f"/api/lists/{excluded['id']}/contacts",
        json={"contact_ids": [target["id"]]},
        headers=headers,
    )

    campaign = client.post(
        "/api/campaigns",
        json={
            "name": "Excluded",
            "list_ids": [included["id"]],
            "exclude_list_ids": [excluded["id"]],
        },
        headers=headers,
    )
    assert campaign.status_code == 201, campaign.text
    assert campaign.json()["total_recipients"] == 2


def test_foreign_list_id_is_rejected(client):
    headers = _headers(client)
    stranger = _headers(client)
    theirs = client.post(
        "/api/lists", json={"name": f"Theirs {uuid.uuid4().hex[:8]}"}, headers=stranger
    ).json()

    response = client.post(
        "/api/campaigns",
        json={"name": "Steal", "list_ids": [theirs["id"]]},
        headers=headers,
    )
    assert response.status_code == 404, response.text


def test_campaign_type_is_validated(client):
    headers = _headers(client)
    response = client.post(
        "/api/campaigns",
        json={"name": "Bad type", "campaign_type": "sms"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_ab_split_sets_variant_weights(client):
    headers = _headers(client)
    created = client.post(
        "/api/ab-tests",
        json={
            "name": "Split test",
            "split_a": 20,
            "split_b": 80,
            "test_type": "subject",
            "winning_metric": "open_rate",
            "variants": [
                {"label": "A", "subject": "A subject", "body": "A body"},
                {"label": "B", "subject": "B subject", "body": "B body"},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert [variant["weight"] for variant in body["variants"]] == [20, 80]
    assert body["split_a"] == 20
    assert body["split_b"] == 80


def test_ab_split_must_total_one_hundred(client):
    headers = _headers(client)
    response = client.post(
        "/api/ab-tests",
        json={
            "name": "Bad split",
            "split_a": 20,
            "split_b": 70,
            "variants": [{"label": "A", "subject": "s", "body": "b"}],
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_winner_requires_sends_before_it_can_be_picked(client):
    headers = _headers(client)
    created = client.post(
        "/api/ab-tests",
        json={
            "name": "No data",
            "variants": [
                {"label": "A", "subject": "s1", "body": "b1"},
                {"label": "B", "subject": "s2", "body": "b2"},
            ],
        },
        headers=headers,
    ).json()

    response = client.post(
        f"/api/ab-tests/{created['id']}/winner", json={}, headers=headers
    )
    assert response.status_code == 409, response.text


def test_winner_can_be_chosen_manually(client):
    headers = _headers(client)
    created = client.post(
        "/api/ab-tests",
        json={
            "name": "Manual winner",
            "variants": [
                {"label": "A", "subject": "s1", "body": "b1"},
                {"label": "B", "subject": "s2", "body": "b2"},
            ],
        },
        headers=headers,
    ).json()

    response = client.post(
        f"/api/ab-tests/{created['id']}/winner",
        json={"variant_label": "B"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["winner_label"] == "B"
    assert body["status"] == "completed"


def test_campaign_analytics_reports_devices_and_ab_results(client):
    headers = _headers(client)
    contact_list, _ = _list_with_contacts(client, headers, 1)
    campaign = client.post(
        "/api/campaigns",
        json={"name": "Analytics", "list_ids": [contact_list["id"]]},
        headers=headers,
    ).json()

    response = client.get(f"/api/campaigns/{campaign['id']}/analytics", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"campaign", "stats", "devices", "countries", "ab_test"}
    assert body["stats"]["total_recipients"] == 1
    assert body["stats"]["spam_complaints"] == 0
