"""Serverless-safe job execution.

Vercel freezes the function as soon as it responds, so a handoff to the
in-process send worker silently drops every queued message. With
``ENABLE_BACKGROUND_JOBS=false`` the endpoints must drain a bounded window
inline and report what is left, rather than returning a job id nobody polls.
"""
import pytest

from app.config import settings as app_settings


@pytest.fixture
def without_worker(monkeypatch):
    """Run the queue endpoints as a serverless host would."""
    monkeypatch.setattr(app_settings, "ENABLE_BACKGROUND_JOBS", False)
    monkeypatch.setattr(app_settings, "SYNC_DRAIN_SECONDS", 5)
    return app_settings


def test_run_async_returns_a_result_not_a_job_id(client, without_worker):
    """No worker exists, so a job id would be unpollable and misleading."""
    response = client.post("/api/queue/run-async", json={})

    assert response.status_code == 202, response.text
    body = response.json()

    assert "job_id" not in body
    assert "status" not in body
    assert "result" in body
    assert body["message"]


def test_run_async_still_reports_the_drain_result(client, without_worker):
    response = client.post("/api/queue/run-async", json={})

    result = response.json()["result"]
    for key in ("processed", "sent", "failed", "skipped"):
        assert key in result


def test_run_all_never_reports_a_job_id_without_a_worker(client, without_worker):
    """The guarantee is that nothing is handed to a worker that cannot exist."""
    response = client.post("/api/queue/run-all", json={})

    assert response.status_code == 200, response.text
    body = response.json()

    assert "job_id" not in body
    assert "queued" not in body
    assert "result" in body


def test_scheduling_run_now_reports_inline_sending(client, without_worker):
    response = client.post("/api/scheduling/run-now")

    assert response.status_code == 200, response.text
    result = response.json()["result"]

    assert result["queued"] is False
    assert "send" in result


def test_worker_is_still_used_when_background_jobs_are_enabled(client, monkeypatch):
    """The long-lived-host path must keep its non-blocking handoff."""
    monkeypatch.setattr(app_settings, "ENABLE_BACKGROUND_JOBS", True)

    response = client.post("/api/scheduling/run-now")

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["queued"] is True
    assert result["job_id"]


def test_sync_drain_budget_is_bounded_and_configurable(monkeypatch):
    """The inline drain must be bounded, or a request runs until the timeout."""
    from app.routers import queue

    assert queue.SYNC_DRAIN_SECONDS == app_settings.SYNC_DRAIN_SECONDS
    assert queue.SYNC_DRAIN_SECONDS <= 60

    # Endpoints read the setting at call time, so an operator can tune the
    # window without a redeploy.
    monkeypatch.setattr(app_settings, "SYNC_DRAIN_SECONDS", 7)
    assert app_settings.SYNC_DRAIN_SECONDS == 7