"""Bounded asynchronous queue sending for high-volume tenants.

``POST /api/queue/run-all`` stays synchronous: a caller that asks for a send gets
the result. ``POST /api/queue/run-async`` instead schedules the same queue pass
on a small worker pool and returns a job id immediately, so a large batch cannot
hold an HTTP request open.

The worker never bypasses ``services/limits.py`` — it runs the identical
``QueueManager.process_queue`` path, so pacing, daily caps and the plan
allowance still gate every individual send.
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

PENDING = "pending"
RUNNING = "running"
COMPLETE = "complete"
FAILED = "failed"


@dataclass
class SendJob:
    id: str
    tenant_id: int
    status: str = PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result,
            "error": self.error,
        }


class SendWorker:
    """Runs queue passes concurrently, bounded by ``SEND_CONCURRENCY``."""

    def __init__(self, concurrency: Optional[int] = None):
        self._concurrency = max(1, int(concurrency or app_settings.SEND_CONCURRENCY))
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._jobs: Dict[str, SendJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._max_jobs = 200

    def get(self, job_id: str) -> Optional[SendJob]:
        return self._jobs.get(job_id)

    def submit(self, tenant_id: int, runner=None) -> SendJob:
        """Schedule one send pass and return its tracked job.

        ``runner`` is an optional zero-argument coroutine function returning the
        pass result; the default is the standard queue pass.
        """
        job = SendJob(id=uuid.uuid4().hex[:16], tenant_id=tenant_id)
        self._jobs[job.id] = job
        self._trim()
        task = asyncio.create_task(self._run(job, runner))
        self._tasks[job.id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(job.id, None))
        return job

    async def _run(self, job: SendJob, runner=None) -> None:
        async with self._semaphore:
            job.status = RUNNING
            job.started_at = datetime.now(timezone.utc)
            try:
                if runner is None:
                    # Default job = "send everything that is ready". A single
                    # queue pass would stop at the pacing rule and deliver one
                    # message, so the worker drains instead.
                    job.result = await drain_queue(tenant_id=job.tenant_id)
                else:
                    job.result = await runner()
                job.status = COMPLETE
            except Exception as exc:  # a failed pass must not kill the worker
                logger.exception("Async send job %s failed", job.id)
                job.error = str(exc)
                job.status = FAILED
            finally:
                job.finished_at = datetime.now(timezone.utc)

    def _trim(self) -> None:
        """Forget the oldest finished jobs so the map cannot grow forever."""
        if len(self._jobs) <= self._max_jobs:
            return
        for job_id in [
            key
            for key, job in self._jobs.items()
            if job.status in {COMPLETE, FAILED}
        ]:
            self._jobs.pop(job_id, None)
            if len(self._jobs) <= self._max_jobs:
                return


_worker: Optional[SendWorker] = None


def get_worker() -> SendWorker:
    """Lazily create the process-wide worker (it needs a running loop)."""
    global _worker
    if _worker is None:
        _worker = SendWorker()
    return _worker


# One queue pass stops as soon as the 60-second pacing rule pauses it, which is
# correct for a timer but wrong for "press Run once and everyone gets an email".
# The drain runner keeps passing until nothing sendable is left, waiting out the
# pacing gap between passes. Limits, caps and eligibility are never bypassed:
# every individual send still goes through ``check_send_allowed``.
DRAIN_MAX_PASSES = 200
DRAIN_MAX_SECONDS = 1800


async def drain_queue(
    tenant_id: Optional[int] = None,
    max_passes: int = DRAIN_MAX_PASSES,
    max_seconds: int = DRAIN_MAX_SECONDS,
) -> Dict[str, Any]:
    """Run queue passes until the tenant's sendable drafts are gone.

    Stops when a pass sends nothing new (nothing sendable, a cap reached, or
    SMTP unconfigured), when ``max_passes``/``max_seconds`` is hit, or when the
    app is shutting down. Returns the merged result plus ``passes`` and
    ``paused`` so a caller can tell "all sent" from "stopped by a limit".
    """
    from app.agents import QueueManager
    from app.services.limits import PACING_SECONDS

    totals: Dict[str, Any] = {
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
        "passes": 0,
        "paused": False,
    }
    deadline = time.monotonic() + max(1, max_seconds)

    for _ in range(max(1, max_passes)):
        result = await QueueManager().process_queue(tenant_id=tenant_id)
        totals["passes"] += 1

        if result.get("error"):
            totals["error"] = result["error"]
            break

        for key in ("processed", "sent", "failed", "skipped"):
            totals[key] += int(result.get(key, 0) or 0)
        totals["details"].extend(result.get("details") or [])

        paused = any(
            detail.get("status") == "paused" for detail in (result.get("details") or [])
        )
        if paused:
            totals["paused"] = True
            if time.monotonic() + PACING_SECONDS >= deadline:
                break
            # Pacing is the only reason worth waiting for: the next draft is
            # ready, just not yet allowed to leave.
            await asyncio.sleep(PACING_SECONDS)
            continue

        # A pass that sent nothing and was not merely paced means there is
        # nothing left this run can do (no drafts, a cap, or no SMTP).
        if int(result.get("sent", 0) or 0) == 0:
            break

    return totals

