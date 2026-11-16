"""Basic tests for Email Orchestrator."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    # Entering the client runs app startup, which creates missing tables.
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    """Test health check endpoint."""
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