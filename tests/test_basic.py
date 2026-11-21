"""Basic tests for Email Orchestrator."""
import pytest
from app.agents import CalendarAgent


def test_health_check(client):
    """Health check endpoint stays public."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]


def test_api_state(client):
    """Test API state endpoint."""
    response = client.get("/api/state")
    assert response.status_code == 200
    data = response.json()
    assert "contacts" in data
    assert "drafts" in data
    assert isinstance(data["contacts"], list)
    assert isinstance(data["drafts"], list)


def test_templates_list(client):
    """Test templates list endpoint."""
    response = client.get("/api/templates")
    assert response.status_code == 200
    data = response.json()
    assert "templates" in data


def test_inbox_list(client):
    """The inbox reports whether IMAP is configured and lists stored mail."""
    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert isinstance(data["messages"], list)


def test_queue_status(client):
    """Queue status reports scheduler state and pending drafts."""
    response = client.get("/api/queue/status")
    assert response.status_code == 200
    data = response.json()
    assert "scheduler" in data
    assert "pending_drafts" in data


def test_redraft_unknown_draft_is_404(client):
    """Redrafting a missing draft must not create or arm anything."""
    response = client.post("/api/drafts/999999/redraft")
    assert response.status_code == 404


def test_agent_method_lifecycle_is_streamed_over_websocket(client):
    """Agent method lifecycle events are sent to connected clients in real time."""
    with client.websocket_connect("/ws/live-logs") as websocket:
        CalendarAgent().available()
        events = [websocket.receive_json() for _ in range(4)]

    assert [(event["scope"], event["status"]) for event in events] == [
        ("agent", "started"),
        ("method", "started"),
        ("method", "completed"),
        ("agent", "completed"),
    ]
    assert all(event["agent"] == "CalendarAgent" for event in events)
    assert all(event["method"] == "available" for event in events)
    assert all("timestamp" in event for event in events)