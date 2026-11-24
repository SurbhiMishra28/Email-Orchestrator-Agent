"""External cron entrypoint.

Hosts that cannot keep a process alive (serverless functions, free tiers that
sleep) never fire APScheduler, so the inbox poll and the paced send worker are
driven by an external scheduler calling this route instead.

Authentication is a shared secret, not a bearer token. The dashboard URL is
public and the app has no sign-in screen, so a route that runs the whole
pipeline cannot rely on the implicit workspace: anyone who found the URL could
trigger sends. The secret is compared in constant time and the route is
disabled outright when ``CRON_SECRET`` is unset.

Sending is drained one tenant at a time. ``QueueManager.process_queue(None)``
resolves a single mailbox for the whole database, which would mail every
tenant's drafts from the first tenant's account; iterating keeps each
workspace on its own mailbox.
"""
import hmac
import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import func

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _authorized(provided: str) -> bool:
    expected = (app_settings.CRON_SECRET or "").strip()
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.strip(), expected)


def _tenants_with_work() -> List[int]:
    """Tenants the automation is allowed to send for right now.

    A tenant must have a sendable draft, a resolvable mailbox, *and* autopilot
    enabled. The autopilot flag is what the in-process scheduler already gates
    on, and it is the only thing that distinguishes a workspace the operator
    opted into unattended sending from one that merely has queued drafts -- a
    leftover test tenant, a half-finished signup, or an account whose mail is
    reviewed by hand. Draining those would mail real people from a mailbox the
    owner never pointed at this pipeline.
    """
    from app.db import Draft, SessionLocal, Settings, Tenant
    from app.services.mailer import is_configured, resolve_smtp_config

    db = SessionLocal()
    try:
        tenant_ids = [
            row[0]
            for row in db.query(Tenant.id)
            .join(Draft, Draft.tenant_id == Tenant.id)
            .join(Settings, Settings.tenant_id == Tenant.id)
            .filter(
                Draft.status.in_(["draft", "blocked"]),
                Settings.AUTOPILOT == True,  # noqa: E712 - SQLAlchemy comparison
            )
            .distinct()
            .all()
        ]
        ready = []
        for tenant_id in tenant_ids:
            try:
                if is_configured(resolve_smtp_config(db, tenant_id)):
                    ready.append(int(tenant_id))
            except Exception as exc:  # one bad row must not stop the tick
                logger.warning("Could not resolve SMTP for tenant %s: %s", tenant_id, exc)
        return ready
    finally:
        db.close()


async def _run_tick() -> Dict[str, Any]:
    """Poll the inbox once, then drain every tenant that can send.

    The whole tick shares one wall-clock budget so the HTTP call returns before
    the external scheduler's timeout. Whatever is left is picked up next tick;
    limits, caps, pacing and the placeholder guard are unchanged.
    """
    from app.main import _poll_inbox_job
    from app.services.send_worker import drain_queue

    result: Dict[str, Any] = {"sending": [], "transport": _transport_label()}

    try:
        await _poll_inbox_job()
        result["inbox"] = "ok"
    except Exception as exc:  # a mailbox outage must not stop the send phase
        logger.warning("Cron inbox poll failed: %s", exc)
        result["inbox"] = f"error: {exc}"

    deadline = time.monotonic() + max(5, app_settings.CRON_MAX_SECONDS)
    for tenant_id in _tenants_with_work():
        remaining = int(deadline - time.monotonic())
        if remaining <= 1:
            result["deferred"] = True
            break
        try:
            totals = await drain_queue(tenant_id=tenant_id, max_seconds=remaining)
            result["sending"].append(
                {
                    "tenant_id": tenant_id,
                    "sent": totals.get("sent", 0),
                    "failed": totals.get("failed", 0),
                    "skipped": totals.get("skipped", 0),
                    "paused": totals.get("paused", False),
                }
            )
        except Exception as exc:
            logger.exception("Cron send pass failed for tenant %s", tenant_id)
            result["sending"].append({"tenant_id": tenant_id, "error": str(exc)})

    return result


@router.post("/tick")
@router.get("/tick")
async def cron_tick(
    x_cron_secret: str = Header(default="", alias="X-Cron-Secret"),
    authorization: str = Header(default=""),
) -> Dict[str, Any]:
    """Run one automation tick: poll the inbox, then drain the send queue.

    Accepts the secret either as ``X-Cron-Secret`` or as ``Authorization: Bearer
    <secret>``, because many cron services only allow custom headers on paid
    tiers.
    """
    if not (app_settings.CRON_SECRET or "").strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Cron endpoint is disabled. Set CRON_SECRET to enable "
                "/api/cron/tick."
            ),
        )

    bearer = ""
    if authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1]

    if not (_authorized(x_cron_secret) or _authorized(bearer)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )

    return await _run_tick()


def _transport_label() -> str:
    """Report the outbound transport so a cron log makes a misconfiguration obvious."""
    from app.services.mailer import active_transport

    return active_transport()


@router.get("/status")
async def cron_status(
    x_cron_secret: str = Header(default="", alias="X-Cron-Secret"),
) -> Dict[str, Any]:
    """Report what the next tick would do, without sending anything."""
    if not _authorized(x_cron_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret"
        )

    from app.config import settings as cfg
    from app.db import Draft, SessionLocal

    db = SessionLocal()
    try:
        pending = (
            db.query(func.count(Draft.id))
            .filter(Draft.status.in_(["draft", "blocked"]))
            .scalar()
            or 0
        )
    finally:
        db.close()

    return {
        "enabled": True,
        "transport": _transport_label(),
        "pending_drafts": int(pending),
        "tenants_with_work": _tenants_with_work(),
        "max_seconds": cfg.CRON_MAX_SECONDS,
        "background_jobs": cfg.ENABLE_BACKGROUND_JOBS,
    }
