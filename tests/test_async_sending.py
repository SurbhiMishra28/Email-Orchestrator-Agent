"""Async sending tests: the worker reports progress and stays tenant-scoped."""
import uuid

from app.services.send_worker import COMPLETE, FAILED, SendWorker


def _fresh_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"async-{suffix}@example.com",
            "password": "async-password-123",
            "name": "Async User",
            "tenant_name": f"Async Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def test_worker_runs_a_submitted_job_to_completion():
    import asyncio

    async def scenario():
        worker = SendWorker(concurrency=2)

        async def runner():
            return {"processed": 3, "sent": 2, "failed": 1, "skipped": 0, "details": []}

        job = worker.submit(tenant_id=42, runner=runner)
        assert job.tenant_id == 42

        for _ in range(50):
            if job.status in {COMPLETE, FAILED}:
                break
            await asyncio.sleep(0.02)

        assert job.status == COMPLETE
        assert job.result["sent"] == 2
        assert job.started_at is not None
        assert job.finished_at is not None
        assert job.to_dict()["job_id"] == job.id

    asyncio.run(scenario())


def test_worker_records_a_failed_pass():
    import asyncio

    async def scenario():
        worker = SendWorker(concurrency=1)

        async def runner():
            raise RuntimeError("smtp exploded")

        job = worker.submit(tenant_id=1, runner=runner)

        for _ in range(50):
            if job.status in {COMPLETE, FAILED}:
                break
            await asyncio.sleep(0.02)

        assert job.status == FAILED
        assert "smtp exploded" in job.error

    asyncio.run(scenario())


def test_worker_bounds_concurrency_and_trims_finished_jobs():
    import asyncio

    async def scenario():
        worker = SendWorker(concurrency=2)
        active = {"current": 0, "peak": 0}

        async def runner():
            active["current"] += 1
            active["peak"] = max(active["peak"], active["current"])
            await asyncio.sleep(0.02)
            active["current"] -= 1
            return {"processed": 1, "sent": 1, "failed": 0, "skipped": 0, "details": []}

        jobs = [worker.submit(tenant_id=1, runner=runner) for _ in range(6)]
        for _ in range(100):
            if all(job.status in {COMPLETE, FAILED} for job in jobs):
                break
            await asyncio.sleep(0.02)

        assert active["peak"] <= 2
        assert all(job.status == COMPLETE for job in jobs)

        # The job map is capped so a long-running process cannot leak.
        worker._max_jobs = 2
        worker._trim()
        assert len(worker._jobs) <= 2

    asyncio.run(scenario())


def test_run_async_returns_a_job_and_reports_it(client):
    headers = _fresh_headers(client)

    queued = client.post("/api/queue/run-async", json={}, headers=headers)
    assert queued.status_code == 202, queued.text
    body = queued.json()
    assert body["status"] in {"pending", "running", "complete", "failed"}
    job_id = body["job_id"]

    status = client.get(f"/api/queue/jobs/{job_id}", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["job_id"] == job_id


def test_run_async_unknown_template_is_a_404(client):
    headers = _fresh_headers(client)
    response = client.post(
        "/api/queue/run-async", json={"template_id": 999999}, headers=headers
    )
    assert response.status_code == 404


def test_jobs_from_another_tenant_are_not_readable(client):
    alpha = _fresh_headers(client)
    beta = _fresh_headers(client)

    queued = client.post("/api/queue/run-async", json={}, headers=alpha)
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["job_id"]

    assert client.get(f"/api/queue/jobs/{job_id}", headers=beta).status_code == 404
    assert client.get("/api/queue/jobs/does-not-exist", headers=alpha).status_code == 404
