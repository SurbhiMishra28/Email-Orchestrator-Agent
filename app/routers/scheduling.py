"""Scheduling control API.

The scheduler itself lives in ``app.main``; these routes report what it is
doing for the caller's tenant and let that tenant turn autopilot on or off
without editing global settings. The scheduler is imported lazily inside the
handlers because ``app.main`` imports the router package at module load.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import settings as app_settings
from app.db import Draft, Log, SessionLocal
from app.deps import current_tenant_id
from app.routers.settings import get_or_create_settings

logger = logging.getLogger(__name__)

router = APIRouter()

JOB_LABELS = {
    "inbox_poll": "Inbox polling",
    "autopilot": "Autopilot pass",
}


class AutopilotToggle(BaseModel):
    enabled: bool
    auto_approve: Optional[bool] = None


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _job_state(job_id: str) -> Dict[str, Any]:
    from app.main import scheduler

    job = scheduler.get_job(job_id)
    if job is None:
        return {
            "id": job_id,
            "label": JOB_LABELS.get(job_id, job_id),
            "scheduled": False,
            "next_run": None,
            "interval_seconds": None,
        }
    return {
        "id": job_id,
        "label": JOB_LABELS.get(job_id, job_id),
        "scheduled": True,
        "next_run": _iso(getattr(job, "next_run_time", None)),
        "interval_seconds": int(job.trigger.interval.total_seconds())
        if hasattr(job.trigger, "interval")
        else None,
    }


@router.get("/status")
def scheduling_status(tenant_id: int = Depends(current_tenant_id)):
    """Report scheduled jobs and the caller's autopilot settings."""
    db = SessionLocal()
    try:
        settings_row = get_or_create_settings(db, tenant_id)
        return {
            "jobs": [_job_state("inbox_poll"), _job_state("autopilot")],
            "autopilot_enabled": bool(settings_row.AUTOPILOT),
            "auto_approve_enabled": bool(settings_row.AUTO_APPROVE),
            "followups_enabled": bool(app_settings.FOLLOWUPS_ENABLED),
            "inbox_poll_minutes": app_settings.IMAP_POLL_MINUTES,
        }
    finally:
        db.close()


@router.post("/autopilot")
def set_autopilot(
    payload: AutopilotToggle, tenant_id: int = Depends(current_tenant_id)
):
    """Turn the caller's autopilot pass on or off.

    Autopilot only runs when both ``AUTOPILOT`` and ``AUTO_APPROVE`` are set,
    so enabling autopilot without an explicit ``auto_approve`` turns it on too;
    disabling autopilot leaves ``AUTO_APPROVE`` as the user had it.
    """
    db = SessionLocal()
    try:
        settings_row = get_or_create_settings(db, tenant_id)

        settings_row.AUTOPILOT = payload.enabled
        if payload.auto_approve is None:
            if payload.enabled:
                settings_row.AUTO_APPROVE = True
        else:
            settings_row.AUTO_APPROVE = payload.auto_approve

        db.add(
            Log(
                message=(
                    f"Autopilot {'enabled' if payload.enabled else 'disabled'} "
                    f"(auto-approve {'on' if settings_row.AUTO_APPROVE else 'off'})"
                ),
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()
        db.refresh(settings_row)

        return {
            "autopilot_enabled": bool(settings_row.AUTOPILOT),
            "auto_approve_enabled": bool(settings_row.AUTO_APPROVE),
        }
    finally:
        db.close()


@router.get("/history")
def scheduling_history(
    limit: int = 20, tenant_id: int = Depends(current_tenant_id)
):
    """Recent scheduler activity for the caller: autopilot passes and sends."""
    limit = max(1, min(limit, 100))
    db = SessionLocal()
    try:
        runs = (
            db.query(Log)
            .filter(
                Log.tenant_id == tenant_id,
                Log.message.like("Autopilot%") | Log.message.like("Queued %"),
            )
            .order_by(Log.timestamp.desc())
            .limit(limit)
            .all()
        )
        sends = (
            db.query(Draft)
            .filter(Draft.tenant_id == tenant_id, Draft.sent_at.isnot(None))
            .order_by(Draft.sent_at.desc())
            .limit(limit)
            .all()
        )

        entries: List[Dict[str, Any]] = [
            {
                "type": "autopilot",
                "message": run.message,
                "level": run.level,
                "timestamp": _iso(run.timestamp),
            }
            for run in runs
        ]
        entries.extend(
            {
                "type": "send",
                "message": f"Sent draft #{draft.id}",
                "level": "info",
                "draft_id": draft.id,
                "timestamp": _iso(draft.sent_at),
            }
            for draft in sends
        )
        entries.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return {"history": entries[:limit], "generated_at": _iso(datetime.now(timezone.utc))}
    finally:
        db.close()


@router.post("/run-now")
async def run_scheduling_now(tenant_id: int = Depends(current_tenant_id)):
    """Run one autopilot pass immediately for the caller's tenant.

    Drafting and reply handling are inline; the paced sending is handed to the
    background worker so this request returns promptly and the user does not
    have to press Run again.
    """
    from app.main import _autopilot_pass
    from app.services.send_worker import get_worker

    result = await _autopilot_pass(tenant_id, send=False)

    job = get_worker().submit(tenant_id)
    result["queued"] = True
    result["job_id"] = job.id

    db = SessionLocal()
    try:
        db.add(
            Log(
                message=(
                    "Autopilot pass run manually: "
                    f"{result.get('intros_drafted', 0)} intros drafted, "
                    f"{result.get('replies_answered', 0)} replies answered, "
                    f"sending queued as job {job.id}"
                ),
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()
    finally:
        db.close()

    return {"message": "Autopilot pass completed", "tenant_id": tenant_id, "result": result}
