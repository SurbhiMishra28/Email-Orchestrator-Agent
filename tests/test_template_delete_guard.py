"""Deleting a template that is still in use must be refused, not crash."""
import uuid


def _template(client, headers):
    response = client.post(
        "/api/templates",
        json={
            "name": f"Guard {uuid.uuid4().hex[:8]}",
            "category": "intro",
            "subject_template": "Hi {{first_name}}",
            "body_template": "Body for {{first_name}}",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_delete_template_in_use_returns_409(client):
    headers = dict(client.headers)
    template = _template(client, headers)

    campaign = client.post(
        "/api/campaigns",
        json={
            "name": f"Guard campaign {uuid.uuid4().hex[:8]}",
            "channel": "email",
            "template_id": template["id"],
        },
        headers=headers,
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]

    blocked = client.delete(f"/api/templates/{template['id']}", headers=headers)
    assert blocked.status_code == 409, blocked.text
    assert "campaign" in blocked.json()["detail"].lower()

    still_there = client.get("/api/templates", headers=headers).json()["templates"]
    assert any(row["id"] == template["id"] for row in still_there)

    assert client.delete(f"/api/campaigns/{campaign_id}", headers=headers).status_code == 200
    freed = client.delete(f"/api/templates/{template['id']}", headers=headers)
    assert freed.status_code == 200, freed.text


def test_delete_unused_template_succeeds(client):
    headers = dict(client.headers)
    template = _template(client, headers)

    deleted = client.delete(f"/api/templates/{template['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    remaining = client.get("/api/templates?active_only=false", headers=headers).json()["templates"]
    assert all(row["id"] != template["id"] for row in remaining)
