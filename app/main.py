"""Main FastAPI application entry point."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query, Body, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings as app_settings
from app.db import (
    Contact,
    Draft,
    Event,
    InboxMessage,
    Log,
    ReplyProcessed,
    SMTPConfig,
    SessionLocal,
    Settings,
    Template,
    Tenant,
    ToolUse,
    init_db,
)
from app.deps import current_tenant_id
from app.models.schemas import ContactOut, DraftOut, SettingsOut
from app.services.provisioning import provision_tenant_defaults
from app import security
from app.live_logs import live_logs
from app.routers import api

logger = logging.getLogger(__name__)

# Reply classifications that mean the recipient wants to keep talking. Used by
# ``_build_analytics`` to report how many clients are interested in the business.
INTERESTED_REPLY_TYPES = ("positive_response", "schedule_call")

DEFAULT_INTRO_SUBJECT = "A quick introduction"
DEFAULT_INTRO_BODY = (
    "Hi {{ first_name or 'there' }},\n\n"
    "I'm reaching out from {{ business_name or 'our team' }}. {{ business_offer }}\n\n"
    "Would you be open to a short conversation to see if this is relevant?\n"
    "{% if calendly_url %}Choose a time: {{ calendly_url }}{% else %}"
    "If so, reply and we can coordinate a time.{% endif %}\n\n"
    "{{ sender_name or 'Best regards' }}"
)


class RunRequest(BaseModel):
    goal: str | None = None


def _rate_limit_key(request: Request) -> str:
    """Key rate limits by tenant rather than by IP address.

    Behind a proxy or on a shared office network many accounts share one IP, so
    an IP-keyed limit throttles innocent tenants together. The tenant claim in
    the bearer token identifies the real consumer; anything unauthenticated
    (health checks, docs) still falls back to the IP.
    """
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            from jose import JWTError, jwt

            from app.auth import ALGORITHM, SECRET_KEY

            claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            tenant_claim = claims.get("tenant_id")
            if tenant_claim is not None:
                return f"tenant:{tenant_claim}"
            subject = claims.get("sub")
            if subject is not None:
                return f"user:{subject}"
        except JWTError:
            pass
    return f"ip:{get_remote_address(request)}"


# Rate limiter
limiter = Limiter(key_func=_rate_limit_key)

# Background scheduler
scheduler = AsyncIOScheduler()


def _iso(value):
    return value.isoformat() if value else None


def _build_analytics(db, tenant_id: int) -> Dict[str, Any]:
    """Aggregate the caller's sending activity for the dashboard.

    Everything here is tenant-scoped: ``sent`` and ``replied`` come from drafts
    and events, so a tenant can never see another tenant's numbers.
    """
    sent = (
        db.query(func.count(Draft.id))
        .filter(Draft.tenant_id == tenant_id, Draft.status == "sent")
        .scalar()
        or 0
    )
    failed = (
        db.query(func.count(Draft.id))
        .filter(Draft.tenant_id == tenant_id, Draft.status == "failed")
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(Draft.id))
        .filter(Draft.tenant_id == tenant_id, Draft.status == "draft")
        .scalar()
        or 0
    )
    replied = (
        db.query(func.count(Event.id))
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == "reply_received",
        )
        .scalar()
        or 0
    )
    auto_replies = (
        db.query(func.count(Event.id))
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == "auto_reply_sent",
        )
        .scalar()
        or 0
    )

    # Follow-ups split into the ones already delivered and the ones the queue
    # still has to send. Both are recognised by the ``followup_for`` marker that
    # services/followups.py writes into ``variables``.
    followups_due = 0
    followups_sent = 0
    for status, variables in (
        db.query(Draft.status, Draft.variables)
        .filter(
            Draft.tenant_id == tenant_id,
            Draft.status.in_(["draft", "sent"]),
        )
        .all()
    ):
        if not isinstance(variables, dict) or not variables.get("followup_for"):
            continue
        if status == "sent":
            followups_sent += 1
        else:
            followups_due += 1

    # Interested clients: distinct contacts whose reply was classified as
    # positive (or an explicit request to schedule a call). The classification
    # lives inside the event's JSON payload, so it is counted in Python rather
    # than with a JSON-path query that SQLite and MariaDB spell differently.
    interested_contacts: set = set()
    reply_type_counts: Dict[str, int] = {}
    for contact_id, data in (
        db.query(Event.contact_id, Event.data)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == "reply_received",
        )
        .all()
    ):
        classification = (data or {}).get("classification") or {}
        reply_type = classification.get("reply_type")
        if not reply_type:
            continue
        reply_type_counts[reply_type] = reply_type_counts.get(reply_type, 0) + 1
        if reply_type in INTERESTED_REPLY_TYPES and contact_id is not None:
            interested_contacts.add(contact_id)

    window_start = datetime.now(timezone.utc) - timedelta(days=13)
    sent_rows = (
        db.query(func.date(Draft.sent_at), func.count(Draft.id))
        .filter(
            Draft.tenant_id == tenant_id,
            Draft.status == "sent",
            Draft.sent_at.isnot(None),
            Draft.sent_at >= window_start,
        )
        .group_by(func.date(Draft.sent_at))
        .all()
    )
    reply_rows = (
        db.query(func.date(Event.timestamp), func.count(Event.id))
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == "reply_received",
            Event.timestamp >= window_start,
        )
        .group_by(func.date(Event.timestamp))
        .all()
    )
    sent_by_day = {str(day): count for day, count in sent_rows}
    replies_by_day = {str(day): count for day, count in reply_rows}

    series = []
    today = datetime.now(timezone.utc).date()
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        series.append(
            {
                "date": key,
                "sent": sent_by_day.get(key, 0),
                "replied": replies_by_day.get(key, 0),
            }
        )

    return {
        "sent": sent,
        "failed": failed,
        "pending": pending,
        "replied": replied,
        "auto_replies": auto_replies,
        "followups_due": followups_due,
        "followups_sent": followups_sent,
        "interested": len(interested_contacts),
        "interested_contacts": sorted(interested_contacts),
        "reply_types": reply_type_counts,
        "reply_rate": round(replied / sent * 100, 1) if sent else 0.0,
        "series": series,
    }


def _build_usage(db, tenant_id: int) -> Dict[str, Any]:
    """Metered usage plus the plan allowance, for the dashboard counter."""
    from app.services.usage import period_totals

    totals = period_totals(db, tenant_id)
    limit = (
        db.query(Tenant.daily_email_limit).filter(Tenant.id == tenant_id).scalar()
    )
    sent_today = totals["today"].get("emails_sent", 0)
    return {
        "today": totals["today"],
        "month": totals["month"],
        "daily_email_limit": limit,
        "daily_remaining": max(0, limit - sent_today) if limit else None,
    }


def get_state_from_db(tenant_id: int) -> Dict[str, Any]:
    """Fetch the caller's state, skipping bad rows instead of blanking the app."""
    db = SessionLocal()
    try:
        contacts = (
            db.query(Contact)
            .filter(Contact.tenant_id == tenant_id)
            .order_by(Contact.id.asc())
            .all()
        )
        drafts = (
            db.query(Draft)
            .filter(Draft.tenant_id == tenant_id)
            .order_by(Draft.id.asc())
            .all()
        )
        logs = (
            db.query(Log)
            .filter(Log.tenant_id == tenant_id)
            .order_by(Log.timestamp.desc())
            .limit(50)
            .all()
        )
        tool_uses = (
            db.query(ToolUse)
            .filter(ToolUse.tenant_id == tenant_id)
            .order_by(ToolUse.timestamp.desc())
            .limit(50)
            .all()
        )
        reply_events = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant_id,
                Event.event_type == "reply_received",
            )
            .order_by(Event.timestamp.desc())
            .limit(50)
            .all()
        )

        settings_row = (
            db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
        )
        from app.services.inbox import resolve_imap_config
        from app.services.mailer import resolve_smtp_config

        smtp_view = resolve_smtp_config(db, tenant_id)
        imap_view = resolve_imap_config(db, tenant_id)

        contacts_out = []
        for contact in contacts:
            try:
                contacts_out.append(ContactOut.model_validate(contact))
            except Exception as exc:
                logger.warning("Skipping invalid contact %s: %s", contact.id, exc)

        drafts_out = []
        for draft in drafts:
            try:
                drafts_out.append(DraftOut.model_validate(draft))
            except Exception as exc:
                logger.warning("Skipping invalid draft %s: %s", draft.id, exc)

        settings_out = None
        if settings_row:
            try:
                settings_out = SettingsOut.model_validate(settings_row)
            except Exception as exc:
                logger.warning("Invalid settings row: %s", exc)

        all_events = [
            {
                "id": log.id,
                "timestamp": _iso(log.timestamp),
                "type": "log",
                "message": log.message,
            }
            for log in logs
        ]
        all_events.extend(
            {
                "id": event.id,
                "timestamp": _iso(event.timestamp),
                "type": "reply_event",
                "event_type": event.event_type,
                "contact_id": event.contact_id,
                "data": event.data,
            }
            for event in reply_events
        )
        all_events.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

        return {
            "contacts": contacts_out,
            "drafts": drafts_out,
            "events": all_events,
            "logs": [
                {
                    "id": log.id,
                    "level": log.level,
                    "message": log.message,
                    "timestamp": _iso(log.timestamp),
                }
                for log in logs
            ],
            "tools": [
                {
                    "id": tool.id,
                    "tool_name": tool.tool_name,
                    "parameters": tool.parameters,
                    "result": tool.result,
                    "success": tool.success,
                    "timestamp": _iso(tool.timestamp),
                }
                for tool in tool_uses
            ],
            "analytics": _build_analytics(db, tenant_id),
            "usage": _build_usage(db, tenant_id),
            "settings": settings_out,
            "smtp": {
                "host": smtp_view.host or None,
                "port": smtp_view.port,
                "user": smtp_view.user or None,
                "sender": smtp_view.sender or None,
                "configured": smtp_view.configured,
                "authenticated": smtp_view.authentication_configured,
                "source": smtp_view.source,
            },
            "imap": imap_view.describe(),
        }
    except SQLAlchemyError as exc:
        logger.error("Database state fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    finally:
        db.close()


def _bootstrap_database() -> None:
    """Repair interrupted sends and provision per-tenant defaults at startup."""
    db = SessionLocal()
    try:
        # A send interrupted by a restart must not stay stuck in "sending".
        interrupted = (
            db.query(Draft)
            .filter(Draft.status == "sending")
            .update(
                {
                    Draft.status: "failed",
                    Draft.error_message: "Send interrupted by server restart",
                },
                synchronize_session=False,
            )
        )
        # Commit even when nothing matched: the UPDATE opened a write
        # transaction, and on SQLite an uncommitted write lock blocks the nested
        # session that provisions the local user below ("database is locked").
        db.commit()
        if interrupted:
            logger.warning("Recovered %s interrupted send(s)", interrupted)

        # Provision defaults for every tenant, including ones created before
        # settings/SMTP became per-tenant. This build is single-user, so the
        # lowest tenant id is the implicit workspace every request runs as.
        from app.db import Tenant
        from app.services.mailer import local_tenant_id

        local_tenant = local_tenant_id(db)

        # Make sure the implicit tenant and user exist, then adopt any rows
        # written before multi-tenancy.
        from app.auth import get_or_create_local_user

        local_user = get_or_create_local_user()
        legacy_tenant_id = local_user.tenant_id
        adopted = 0
        for model in (
            Contact,
            Draft,
            Event,
            Log,
            ToolUse,
            Template,
            SMTPConfig,
            Settings,
            InboxMessage,
            ReplyProcessed,
        ):
            adopted += (
                db.query(model)
                .filter(model.tenant_id.is_(None))
                .update(
                    {model.tenant_id: legacy_tenant_id},
                    synchronize_session=False,
                )
            )
        db.commit()
        if adopted:
            logger.info(
                "Assigned %s legacy row(s) to local tenant %s",
                adopted,
                legacy_tenant_id,
            )

        tenant_ids = [row[0] for row in db.query(Tenant.id).all()]
        if tenant_ids:
            for tenant_id in tenant_ids:
                provision_tenant_defaults(
                    db,
                    tenant_id,
                    inherit_environment=tenant_id == local_tenant,
                )
        else:
            # A brand-new database: keep the legacy global row until the first
            # request provisions the implicit tenant.
            if not db.query(Settings).first():
                db.add(
                    Settings(
                        goal=app_settings.DEFAULT_GOAL,
                        business_name=app_settings.DEFAULT_BUSINESS_NAME,
                        business_offer=app_settings.DEFAULT_BUSINESS_OFFER,
                    )
                )
            if not db.query(SMTPConfig).first():
                db.add(SMTPConfig())
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Email Orchestrator...")
    # Schema creation and workspace provisioning. These are idempotent, but on
    # a serverless host every cold start would repeat the DDL checks against the
    # managed database, which is slow and races between concurrent instances.
    # Such a deployment sets AUTO_INIT_DB=false and runs
    # ``python scripts/init_db.py`` once instead.
    database_ready = True
    if not app_settings.AUTO_INIT_DB:
        logger.info(
            "AUTO_INIT_DB=false: skipping schema creation and provisioning at "
            "startup. Run 'python scripts/init_db.py' once per database."
        )
    else:
        try:
            # DDL goes through the direct endpoint when the platform exposes one
            # (Neon's DATABASE_URL_UNPOOLED). The pooled endpoint multiplexes
            # transactions and cannot be used for schema work.
            from app.db import direct_engine

            init_db(engine_override=direct_engine())
        except SQLAlchemyError as exc:
            database_ready = False
            logger.error(
                "Database unavailable at startup (%s). The app will keep running "
                "and /health will report degraded. Check DATABASE_URL.",
                exc,
            )

        if database_ready:
            try:
                _bootstrap_database()
            except Exception as exc:  # provisioning must never block serving
                logger.error("Startup provisioning failed: %s", exc)

    # Scheduled work: inbox polling, follow-up drafting and opt-in autopilot.
    # On a serverless host (ENABLE_BACKGROUND_JOBS=false) the process is frozen
    # between requests, so an interval scheduler would never fire and would
    # only add startup cost. The same work stays reachable on demand through
    # /api/scheduling/run-now and /api/inbox/sync.
    if app_settings.ENABLE_BACKGROUND_JOBS and database_ready:
        scheduler.add_job(
            _poll_inbox_job,
            "interval",
            minutes=max(1, app_settings.IMAP_POLL_MINUTES),
            id="inbox_poll",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            _autopilot_job,
            "interval",
            minutes=5,
            id="autopilot",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if not scheduler.running:
            scheduler.start()
    else:
        logger.info(
            "Background jobs not started (ENABLE_BACKGROUND_JOBS=%s, database_ready=%s)",
            app_settings.ENABLE_BACKGROUND_JOBS,
            database_ready,
        )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Email Orchestrator...")
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _tenants_with_inbox(tenant_ids) -> list:
    """Filter ``tenant_ids`` down to the ones with their own resolvable mailbox.

    Inbox polling must never read one mailbox on behalf of another tenant: the
    rows it writes carry ``tenant_id``, so a shared mailbox would duplicate the
    operator's correspondence into every account. The lookup is a cheap series
    of row reads, so it stays synchronous; only the IMAP round-trip is offloaded.
    """
    from app.services.inbox import resolve_imap_config

    db = SessionLocal()
    try:
        return [
            tenant_id
            for tenant_id in tenant_ids
            if resolve_imap_config(db, tenant_id).configured
        ]
    finally:
        db.close()


async def _poll_inbox_job():
    """Fetch new mail for every tenant that has its own IMAP credentials."""
    from fastapi.concurrency import run_in_threadpool

    from app.services.inbox import sync_inbox

    db = SessionLocal()
    try:
        tenant_ids = [row[0] for row in db.query(Tenant.id).all()]
    finally:
        db.close()

    for tenant_id in _tenants_with_inbox(tenant_ids):
        try:
            await run_in_threadpool(sync_inbox, 25, tenant_id)
        except Exception as exc:  # a mailbox outage must not stop the scheduler
            logger.warning("Inbox poll failed for tenant %s: %s", tenant_id, exc)


async def _autopilot_job():
    """Run the queue per tenant, only for tenants that opted in."""
    from fastapi.concurrency import run_in_threadpool

    from app.agents import QueueManager
    from app.services.inbox import is_configured, sync_inbox

    db = SessionLocal()
    try:
        tenants = [
            (row[0], bool(row[1] and row[2]))
            for row in db.query(
                Settings.tenant_id, Settings.AUTOPILOT, Settings.AUTO_APPROVE
            ).all()
        ]
        enabled_tenant_ids = [tenant_id for tenant_id, enabled in tenants if enabled]
        legacy_enabled = False
        if not tenants:
            row = db.query(Settings).first()
            legacy_enabled = bool(row and row.AUTOPILOT and row.AUTO_APPROVE)
    finally:
        db.close()

    if not enabled_tenant_ids and not legacy_enabled:
        return

    for tenant_id in enabled_tenant_ids or [None]:
        try:
            await _run_autopilot_for_tenant(
                tenant_id, run_in_threadpool, sync_inbox, is_configured, QueueManager
            )
        except Exception as exc:
            logger.warning("Autopilot pass failed for tenant %s: %s", tenant_id, exc)


async def _run_autopilot_for_tenant(
    tenant_id, run_in_threadpool, sync_inbox, is_configured, QueueManager, send=True
):
    """One full agent pass for a tenant, in the order the pipeline expects.

    Draft intros for contacts that have none, pull new replies and answer them,
    queue due follow-ups, then send everything through the queue.

    Sending drains the queue rather than making a single pass: one pass stops at
    the 60-second pacing rule, which would deliver a single email per Run. Every
    individual send still passes ``check_send_allowed``, so caps and pacing are
    respected; the pass simply keeps going until the queue is empty.

    ``send=False`` stops after drafting so a caller can hand the (slow, paced)
    sending to a background worker and still answer the HTTP request promptly.
    """
    from app.services.outreach import create_intro_drafts
    from app.services.send_worker import drain_queue

    intro = await create_intro_drafts(tenant_id=tenant_id)

    if is_configured(tenant_id):
        try:
            await run_in_threadpool(sync_inbox, 100, tenant_id)
        except Exception as exc:
            logger.warning("Autopilot inbox sync failed: %s", exc)

    replies = await _process_incoming_replies(tenant_id)
    if app_settings.FOLLOWUPS_ENABLED:
        from app.services.followups import generate_followups

        await generate_followups(tenant_id=tenant_id)

    if send:
        result = await drain_queue(tenant_id=tenant_id)
    else:
        result = {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
            "deferred": True,
        }

    if result.get("error"):
        logger.warning("Autopilot queue pass failed: %s", result["error"])
    result["intros_drafted"] = intro.get("created", 0)
    result["replies_answered"] = replies
    return result


async def _autopilot_pass(tenant_id: Optional[int], send: bool = True) -> Dict[str, Any]:
    """Run one autopilot pass for a single tenant and report what happened.

    Shared by the scheduled job and ``POST /api/scheduling/run-now`` so the
    manual trigger and the timer run exactly the same code path.
    """
    from fastapi.concurrency import run_in_threadpool

    from app.agents import QueueManager
    from app.services.inbox import is_configured, sync_inbox

    return await _run_autopilot_for_tenant(
        tenant_id, run_in_threadpool, sync_inbox, is_configured, QueueManager, send=send
    ) or {}


def _record_bounce(db, msg: "InboxMessage", sender_email: str) -> int:
    """Blacklist every address a delivery-failure report says is dead.

    A hard bounce is the only reliable signal that a mailbox does not exist, so
    the contact is marked ineligible and blacklisted and its outstanding drafts
    are failed rather than retried. Returns how many contacts were blacklisted.
    """
    from app.db import Campaign
    from app.services.bounces import failed_recipients

    addresses = failed_recipients(msg.subject or "", msg.snippet or "", sender_email)
    blacklisted = 0
    for address in addresses:
        contact_query = db.query(Contact).filter(
            func.lower(Contact.email) == address
        )
        if msg.tenant_id is not None:
            contact_query = contact_query.filter(Contact.tenant_id == msg.tenant_id)
        contact = contact_query.first()
        if not contact:
            continue

        contact.email_blacklisted = True
        contact.eligible_to_email = False
        blacklisted += 1

        drafts = (
            db.query(Draft)
            .filter(
                Draft.contact_id == contact.id,
                Draft.status.in_(["draft", "blocked", "sending"]),
            )
            .all()
        )
        for draft in drafts:
            draft.status = "failed"
            draft.error_message = f"Recipient bounced: {address}"

        campaign_ids = {
            draft.campaign_id for draft in drafts if draft.campaign_id is not None
        }
        for campaign_id in campaign_ids:
            campaign = (
                db.query(Campaign)
                .filter(Campaign.id == campaign_id)
                .first()
            )
            if campaign is not None:
                campaign.bounced = (campaign.bounced or 0) + 1

        db.add(
            Log(
                message=(
                    f"Blacklisted {address} after a delivery failure "
                    f"({len(drafts)} draft(s) failed)"
                ),
                level="warning",
                tenant_id=contact.tenant_id,
            )
        )

    if blacklisted:
        db.commit()
    return blacklisted


async def _process_incoming_replies(tenant_id: Optional[int] = None) -> int:
    """Classify every unprocessed inbox message and auto-answer it.

    Runs with no human in the loop: the reply is matched to a contact, classified
    and answered in the same pass, then the queue sends the answer. Returns how
    many automatic replies were queued.
    """
    from app.agents import ReplyAnalyzerAgent, AutoResponder
    from app.services.bounces import looks_like_bounce
    from app.services.usage import REPLIES_RECEIVED, record_usage

    db = SessionLocal()
    replies_queued = 0
    try:
        message_query = db.query(InboxMessage).filter(
            InboxMessage.processed == False
        )
        if tenant_id is not None:
            message_query = message_query.filter(InboxMessage.tenant_id == tenant_id)
        messages = (
            message_query.order_by(InboxMessage.received_at.asc())
            .limit(100)
            .all()
        )
        if not messages:
            return 0
        
        for msg in messages:
            msg_uid = msg.uid or ""
            if not msg_uid:
                continue
            
            sender_email = extract_email_from_sender(msg.sender or "")
            if not sender_email:
                msg.processed = True
                msg.processed_at = datetime.now(timezone.utc)
                db.commit()
                continue

            # A delivery failure must be handled before contact matching: the
            # report comes from a mail system, and the contact it matters for
            # is the address named inside it. Never auto-reply to a bounce.
            if looks_like_bounce(msg.subject or "", msg.snippet or "", msg.sender or ""):
                blacklisted = _record_bounce(db, msg, sender_email)
                msg.processed = True
                msg.processed_at = datetime.now(timezone.utc)
                db.commit()
                if blacklisted:
                    logger.warning(
                        "Inbox message %s was a bounce; blacklisted %s recipient(s)",
                        msg_uid,
                        blacklisted,
                    )
                continue

            # Nobody reads an unmonitored mailbox, so answering one wastes a
            # send and can start a loop between two autoresponders.
            if is_unattended_sender(sender_email):
                msg.processed = True
                msg.processed_at = datetime.now(timezone.utc)
                db.commit()
                continue

            # Find matching contact within the same tenant as the message
            contact_query = db.query(Contact).filter(
                func.lower(Contact.email) == sender_email
            )
            if msg.tenant_id is not None:
                contact_query = contact_query.filter(
                    Contact.tenant_id == msg.tenant_id
                )
            contact = contact_query.first()
            if not contact:
                msg.processed = True
                msg.processed_at = datetime.now(timezone.utc)
                db.commit()
                continue
            
            # Check if we already processed this message by UID. UIDs are only
            # unique inside one mailbox, so the lookup must be tenant-scoped.
            processed_query = db.query(ReplyProcessed).filter(
                ReplyProcessed.message_uid == msg_uid
            )
            if msg.tenant_id is not None:
                processed_query = processed_query.filter(
                    ReplyProcessed.tenant_id == msg.tenant_id
                )
            existing_processed = processed_query.first()
            if existing_processed:
                msg.processed = True
                msg.processed_at = datetime.now(timezone.utc)
                db.commit()
                continue  # Skip already processed messages
            
            # Classify the reply. The pipeline meters the reply itself below,
            # after de-duplicating it, so the built-in usage metric is disabled
            # here: recording in both places counted every reply twice.
            agent = ReplyAnalyzerAgent(contact_id=contact.id)
            try:
                classification = agent.analyze_reply(
                    subject=msg.subject or "",
                    body=msg.snippet or "",
                    sender_email=sender_email,
                    record_usage_metric=False,
                )
            except Exception:
                logger.exception("Could not classify reply %s", msg_uid)
                continue
            finally:
                agent.close()

            db.add(
                ReplyProcessed(
                    message_uid=msg_uid,
                    contact_id=contact.id,
                    tenant_id=msg.tenant_id,
                )
            )
            record_usage(
                db,
                msg.tenant_id if msg.tenant_id is not None else tenant_id,
                REPLIES_RECEIVED,
            )
            msg.processed = True
            msg.processed_at = datetime.now(timezone.utc)
            db.commit()

            auto_responder = AutoResponder(contact_id=contact.id)
            try:
                response = auto_responder.generate_response(
                    classification=classification,
                    original_subject=msg.subject or "",
                    original_body=msg.snippet or "",
                    sender_email=sender_email,
                )
                # AutoResponder only has templates for reply types that need an
                # answer (spam and acknowledgements return None), so no human
                # gate is needed here: the pipeline answers by itself.
                if response:
                    send_result = auto_responder.send_response(response)
                    auto_responder.log_interaction(
                        event_id=classification.get("event_id") or 0,
                        send_result=send_result,
                    )
                    if send_result.get("success"):
                        replies_queued += 1
            except Exception:
                logger.exception("Could not send automatic reply for inbox message %s", msg_uid)
            finally:
                auto_responder.close()

        if replies_queued > 0:
            db.add(
                Log(
                    message=f"Queued {replies_queued} automatic reply/replies",
                    level="info",
                    tenant_id=tenant_id,
                )
            )
            db.commit()
        return replies_queued
            
    except Exception as exc:
        logger.warning("Reply processing failed: %s", exc)
        return 0
    finally:
        db.close()


def extract_email_from_sender(sender: str) -> str:
    """Extract email address from sender string."""
    from email.utils import parseaddr

    return parseaddr(sender or "")[1].strip().lower()


def is_unattended_sender(email: str) -> bool:
    """True for a mailbox no human reads (daemons, no-reply, abuse desks).

    Replying to one of these is always wasted: nobody sees the answer, and an
    autoresponder at the far end can bounce the reply back into a loop.
    """
    from app.services.recipients import SYSTEM_LOCAL_PARTS

    local = (email or "").split("@", 1)[0].strip().lower()
    if not local:
        return False
    return local in SYSTEM_LOCAL_PARTS or local in {
        "mailer-daemon",
        "mail-daemon",
        "mailerdaemon",
        "abuse",
    }


app = FastAPI(
    title="Email Orchestrator API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS for frontend. Credentials cannot be combined with a wildcard origin.
cors_origins = [
    origin.strip()
    for origin in app_settings.CORS_ORIGINS.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP Basic auth. Installed after CORS so a rejected request still carries the
# CORS headers and the browser can report the 401 instead of a CORS error.
security.install(app)

# Cache the built SPA's content-hashed assets aggressively.
#
# Vite emits ``/assets/index-<hash>.js`` with the hash in the filename, so the
# bytes for a given URL can never change. Without a cache header the browser
# revalidates the 275 kB bundle on every load, and on a serverless host each of
# those revalidations is a full function invocation. The HTML shell must stay
# live because it points at the current hash.
@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health")
@app.get("/health/")
def health_check():
    """Health check endpoint.

    Returns 503 when the database is unreachable so a platform probe fails the
    deploy instead of reporting a process that cannot serve any request as up.
    """
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_healthy = True
    except SQLAlchemyError:
        db_healthy = False
    finally:
        db.close()

    payload = {
        "status": "healthy" if db_healthy else "degraded",
        "checks": {
            "database": {"healthy": db_healthy, "error": None if db_healthy else "Connection failed"}
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return payload if db_healthy else JSONResponse(status_code=503, content=payload)


# Short-lived per-tenant cache for the dashboard state payload.
#
# ``/api/state`` fans out to ~8 queries plus Pydantic validation; on a managed
# database reached over the public internet that is ~1s of round-trips. The SPA
# refetches on every tab switch and on a 10s poll, so without a cache each of
# those pays the full cost. A 3s TTL collapses bursts (rapid tab switches, the
# poll landing just after a mutation) without showing stale data for long: the
# client already refetches explicitly after every mutation.
_STATE_CACHE: Dict[int, tuple] = {}
_STATE_CACHE_TTL = 3.0


@app.get("/api/state")
@app.get("/api/state/")
def get_state(
    refresh: bool = Query(False),
    tenant_id: int = Depends(current_tenant_id),
):
    """Get the caller's application state for the frontend.

    ``?refresh=1`` bypasses the short-lived cache, for callers that must see a
    write immediately rather than within the TTL.
    """
    import time as _time

    now = _time.monotonic()
    if not refresh:
        cached = _STATE_CACHE.get(tenant_id)
        if cached and (now - cached[0]) < _STATE_CACHE_TTL:
            return cached[1]

    state = get_state_from_db(tenant_id)
    if isinstance(state, dict):
        # The frontend keys its live-log socket off this flag so a host that
        # cannot hold a WebSocket (any serverless platform) renders the log as
        # static instead of reconnecting forever.
        state["live_logs"] = app_settings.ENABLE_LIVE_LOGS
        _STATE_CACHE[tenant_id] = (now, state)
    return state


@app.middleware("http")
async def _state_cache_headers(request, call_next):
    """Let the browser reuse the state payload for a few seconds.

    The SPA polls ``/api/state`` every 10s and refetches on every tab switch. On
    serverless each of those is a fresh ~1s invocation, and the per-instance
    cache above cannot help because consecutive requests often land on different
    instances. A short ``max-age`` lets the browser serve those from its own
    cache, which is the only layer shared across instances. Mutations still show
   up immediately because the client refetches with ``?refresh=1``.
    """
    response = await call_next(request)
    if request.url.path in ("/api/state", "/api/state/"):
        response.headers["Cache-Control"] = "private, max-age=3"
    return response


@app.get("/api/usage")
def get_usage(tenant_id: int = Depends(current_tenant_id)):
    """Report the caller's metered usage for today and this month."""
    db = SessionLocal()
    try:
        return {"tenant_id": tenant_id, **_build_usage(db, tenant_id)}
    finally:
        db.close()


if app_settings.ENABLE_LIVE_LOGS:

    @app.websocket("/ws/live-logs")
    async def live_agent_logs(websocket: WebSocket):
        """Stream transient agent method lifecycle events to connected clients."""
        await websocket.accept()
        queue = live_logs.subscribe()

        async def send_events():
            while True:
                await websocket.send_json(await queue.get())

        sender = asyncio.create_task(send_events())
        try:
            async for _ in websocket.iter_text():
                pass
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
            live_logs.unsubscribe(queue)

else:
    logger.info(
        "Live log WebSocket disabled (ENABLE_LIVE_LOGS=false); /ws/live-logs "
        "is not registered"
    )


@app.post("/api/run")
@app.post("/api/run/")
@limiter.limit("5/minute")
async def run_orchestrator(
    request: Request,
    payload: RunRequest | None = None,
    goal: str = Query(None),
    tenant_id: int = Depends(current_tenant_id),
):
    """Run one full autonomous pass for the caller's tenant.

    Same code path as the scheduled autopilot job: draft intros for contacts
    without outreach, sync the inbox, answer replies, queue follow-ups and send
    through the queue. Nothing waits for approval.

    Drafting and reply handling happen inline so the response can report them.
    Sending is queued on the background worker instead of draining here: pacing
    allows one send per 60 seconds, so a real list would hold the request open
    for a long time. ``result.queued`` says the sending continues server-side.

    A serverless host has no background worker: the process is frozen the
    moment the response is sent, so a handoff would silently drop every
    remaining message. There the queue is drained inline for a bounded window
    and the rest is left for the next cron tick.
    """
    requested_goal = (payload.goal if payload and payload.goal else goal) or None
    db = SessionLocal()
    try:
        settings_row = (
            db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
        )
        if requested_goal and settings_row:
            settings_row.goal = requested_goal
            db.commit()
        resolved_goal = requested_goal or (
            settings_row.goal if settings_row else app_settings.DEFAULT_GOAL
        )
    finally:
        db.close()

    result = await _autopilot_pass(tenant_id, send=False)

    if app_settings.ENABLE_BACKGROUND_JOBS:
        from app.services.send_worker import get_worker

        job = get_worker().submit(tenant_id)
        result["queued"] = True
        result["job_id"] = job.id
    else:
        # No worker exists to hand off to, and the response would abandon the
        # queue. Drain what fits in the window and say what is left.
        from app.services.send_worker import drain_queue

        drained = await drain_queue(
            tenant_id=tenant_id, max_seconds=app_settings.SYNC_DRAIN_SECONDS
        )
        result["send"] = drained

        db = SessionLocal()
        try:
            remaining = (
                db.query(Draft)
                .filter(
                    Draft.tenant_id == tenant_id,
                    Draft.status.in_(["draft", "blocked"]),
                )
                .count()
            )
        finally:
            db.close()

        result["paused"] = remaining > 0
        result["remaining"] = int(remaining)

    return {
        "message": "Autopilot run started",
        "goal": resolved_goal,
        "job_id": result.get("job_id"),
        "result": result,
    }


# Include API router
app.include_router(api.router, prefix="/api")

# Mount static files for frontend
frontend_public = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

# Redirect /index.html to / for proper SPA routing
@app.get("/index.html", include_in_schema=False)
def redirect_index_html():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/")

# Serve built frontend if dist exists
class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException

        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            # Never rewrite API/WebSocket or missing asset requests.
            full_path = scope.get("path", "") or path
            if full_path.startswith(("/api/", "/ws/", "api/", "ws/")):
                raise
            if os.path.splitext(path)[1]:
                raise
            return await super().get_response("index.html", scope)


# Serve the built frontend when this process serves static files itself
# (local development and any long-lived host).
#
# Vercel is included here on purpose. Its Python runtime routes every request
# that is not a build output through the function, so the SPA has to be served
# by FastAPI rather than the CDN. ``vercel.json`` builds the SPA into
# ``app/static`` so the single ``app/**`` include glob ships it inside the
# function bundle.
app_static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
static_dir = (
    app_static
    if os.path.exists(app_static)
    else (frontend_dist if os.path.exists(frontend_dist) else None)
)
if static_dir:
    try:
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="frontend-static")
        logger.info("Serving the built frontend from %s", static_dir)
    except (RuntimeError, OSError):
        pass
if not static_dir and os.path.exists(frontend_public):
    # Fallback to serving index.html from public (development mode).
    @app.get("/", include_in_schema=False)
    def serve_index():
        """Serve the frontend index.html at root."""
        from fastapi.responses import FileResponse
        index_path = os.path.join(frontend_public, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not built. Run 'npm run build' in frontend/ directory."}


if __name__ == "__main__":
    import uvicorn
    # Local tool with no user accounts: bind to loopback so contacts and
    # SMTP settings are not exposed on the LAN by default.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)