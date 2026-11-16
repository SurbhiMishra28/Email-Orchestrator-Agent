"""Main FastAPI application entry point."""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings as app_settings
from app.db import (
    Contact,
    Draft,
    Event,
    Log,
    SMTPConfig,
    SessionLocal,
    Settings,
    Template,
    ToolUse,
    init_db,
)
from app.models.schemas import ContactOut, DraftOut, SettingsOut
from app.routers import api

logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    goal: str | None = None


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Background scheduler
scheduler = AsyncIOScheduler()


def _iso(value):
    return value.isoformat() if value else None


def get_state_from_db() -> Dict[str, Any]:
    """Fetch current state, skipping bad rows instead of blanking the app."""
    db = SessionLocal()
    try:
        contacts = db.query(Contact).all()
        drafts = db.query(Draft).all()
        logs = db.query(Log).order_by(Log.timestamp.desc()).limit(50).all()
        tool_uses = db.query(ToolUse).order_by(ToolUse.timestamp.desc()).limit(50).all()
        reply_events = (
            db.query(Event)
            .filter(Event.event_type == "reply_received")
            .order_by(Event.timestamp.desc())
            .limit(50)
            .all()
        )

        settings_row = db.query(Settings).first()
        smtp_config = db.query(SMTPConfig).first()

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
            "analytics": {},
            "settings": settings_out,
            "smtp": {
                "host": smtp_config.host if smtp_config else None,
                "port": smtp_config.port if smtp_config else 587,
                "user": smtp_config.user if smtp_config else None,
                "sender": smtp_config.sender if smtp_config else None,
                "configured": smtp_config.configured if smtp_config else False,
            },
        }
    except SQLAlchemyError as exc:
        logger.error("Database state fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Email Orchestrator...")
    init_db()
    
    # Initialize default data
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
        if interrupted:
            db.commit()
            logger.warning("Recovered %s interrupted send(s)", interrupted)

        # Check if settings exist
        if not db.query(Settings).first():
            default_settings = Settings(
                goal=app_settings.DEFAULT_GOAL,
                business_name=app_settings.DEFAULT_BUSINESS_NAME,
                business_offer=app_settings.DEFAULT_BUSINESS_OFFER
            )
            db.add(default_settings)
            db.commit()
        
        # Seed SMTP settings from the environment when the database has none yet.
        smtp_row = db.query(SMTPConfig).first()
        if not smtp_row:
            smtp_row = SMTPConfig()
            db.add(smtp_row)

        if not smtp_row.host and app_settings.DEFAULT_SMTP_HOST:
            smtp_row.host = app_settings.DEFAULT_SMTP_HOST
        if app_settings.DEFAULT_SMTP_PORT:
            smtp_row.port = app_settings.DEFAULT_SMTP_PORT
        if not smtp_row.user and app_settings.DEFAULT_SMTP_USER:
            smtp_row.user = app_settings.DEFAULT_SMTP_USER
        if not smtp_row.password and app_settings.DEFAULT_SMTP_PASSWORD:
            smtp_row.password = app_settings.DEFAULT_SMTP_PASSWORD
        if not smtp_row.sender and app_settings.DEFAULT_SMTP_SENDER:
            smtp_row.sender = app_settings.DEFAULT_SMTP_SENDER

        smtp_row.configured = bool(smtp_row.host and (smtp_row.sender or smtp_row.user))
        smtp_row.authentication_configured = bool(smtp_row.user and smtp_row.password)
        db.commit()
        
        # Create default templates if not exist
        if db.query(Template).count() == 0:
            templates = [
                Template(name="Intro Email", category="intro", subject_template="Quick intro - {{first_name}}?", body_template="Hi {{first_name}},\n\nI hope you're doing well at {{company}}. I'm reaching out because I noticed you might be interested in [solution]..."),
                Template(name="Follow-up", category="followup", subject_template="Following up", body_template="Hi {{first_name}},\n\nJust wanted to follow up on my previous email..."),
            ]
            for t in templates:
                db.add(t)
            db.commit()
    finally:
        db.close()
    
    # Scheduled work: inbox polling, follow-up drafting and opt-in autopilot.
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
        _followup_job,
        "interval",
        hours=6,
        id="followups",
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
    scheduler.start()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Email Orchestrator...")
    scheduler.shutdown()


async def _poll_inbox_job():
    """Fetch new mail when IMAP credentials are present."""
    from fastapi.concurrency import run_in_threadpool

    from app.services.inbox import is_configured, sync_inbox

    if not is_configured():
        return
    try:
        await run_in_threadpool(sync_inbox, 25)
    except Exception as exc:  # a mailbox outage must not stop the scheduler
        logger.warning("Inbox poll failed: %s", exc)


async def _followup_job():
    """Draft (never send) follow-ups that are due."""
    from app.services.followups import generate_followups

    if not app_settings.FOLLOWUPS_ENABLED:
        return
    try:
        await generate_followups()
    except Exception as exc:
        logger.warning("Follow-up generation failed: %s", exc)


async def _autopilot_job():
    """Run the queue in the background only when the user opted in."""
    from app.agents import QueueManager

    db = SessionLocal()
    try:
        row = db.query(Settings).first()
        enabled = bool(row and row.AUTOPILOT and row.AUTO_APPROVE)
    finally:
        db.close()
    if not enabled:
        return
    try:
        await QueueManager().process_queue()
        # Also process incoming replies for auto-response
        await _process_incoming_replies()
    except Exception as exc:
        logger.warning("Autopilot pass failed: %s", exc)


async def _process_incoming_replies():
    """Process incoming inbox messages and auto-respond to replies.
    
    This function:
    1. Fetches new inbox messages
    2. Matches senders to contacts
    3. Classifies each reply
    4. Generates and sends appropriate auto-replies
    """
    from app.services.inbox import fetch_recent
    from app.agents import ReplyAnalyzerAgent, AutoResponder, SenderAgent
    from app.db import Event, SMTPConfig, ReplyProcessed, InboxMessage
    
    db = SessionLocal()
    try:
        # Get new messages from inbox
        messages = fetch_recent(10)
        if not messages:
            return
        
        smtp_config = db.query(SMTPConfig).first()
        sender_agent = SenderAgent(smtp_config=smtp_config)
        
        replies_processed = 0
        for msg in messages:
            msg_uid = msg.get("uid", "")
            if not msg_uid:
                continue
            
            sender_email = extract_email_from_sender(msg.get("sender", ""))
            if not sender_email:
                continue
            
            # Find matching contact
            contact = db.query(Contact).filter(Contact.email == sender_email).first()
            if not contact:
                continue
            
            # Check if we already processed this message by UID
            existing_processed = db.query(ReplyProcessed).filter(
                ReplyProcessed.message_uid == msg_uid
            ).first()
            if existing_processed:
                continue  # Skip already processed messages
            
            # Classify the reply
            agent = ReplyAnalyzerAgent(contact_id=contact.id)
            classification = agent.analyze_reply(
                subject=msg.get("subject", ""),
                body=msg.get("snippet", ""),
                sender_email=sender_email
            )
            
            # Generate auto-response
            auto_responder = AutoResponder(
                contact_id=contact.id,
                smtp_config=smtp_config,
                sender_agent=sender_agent
            )
            
            response = auto_responder.generate_response(
                classification=classification,
                original_subject=msg.get("subject", ""),
                original_body=msg.get("snippet", ""),
                sender_email=sender_email
            )
            
            if response and not classification.get("needs_human_review", False):
                # Send the auto-response
                send_result = auto_responder.send_response(response)
                auto_responder.log_interaction(
                    event_id=classification.get("event_id", 0),
                    send_result=send_result
                )
                replies_processed += 1
                
                # Mark message as processed
                processed = ReplyProcessed(
                    message_uid=msg_uid,
                    contact_id=contact.id,
                )
                db.add(processed)
            
            # Mark inbox message as processed
            inbox_msg = db.query(InboxMessage).filter(InboxMessage.uid == msg_uid).first()
            if inbox_msg:
                inbox_msg.processed = True
                inbox_msg.processed_at = datetime.now(timezone.utc)
            
            agent.close()
            auto_responder.close()
        
        sender_agent.close()
        
        if replies_processed > 0:
            db.add(Log(message=f"Auto-processed {replies_processed} incoming reply(ies)", level="info"))
            db.commit()
            
    except Exception as exc:
        logger.warning("Reply processing failed: %s", exc)
    finally:
        db.close()


def extract_email_from_sender(sender: str) -> str:
    """Extract email address from sender string."""
    import re
    match = re.search(r'[<"(]([^>")]+@[^>")]+)[>")]', sender)
    if match:
        return match.group(1).lower()
    return sender.lower() if "@" in sender else ""


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


@app.get("/health")
@app.get("/health/")
def health_check():
    """Health check endpoint."""
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

    return {
        "status": "healthy" if db_healthy else "degraded",
        "checks": {
            "database": {"healthy": db_healthy, "error": None if db_healthy else "Connection failed"}
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/state")
@app.get("/api/state/")
def get_state():
    """Get current application state for the frontend."""
    return get_state_from_db()


@app.post("/api/run")
@app.post("/api/run/")
@limiter.limit("5/minute")
async def run_orchestrator(
    request: Request,
    payload: RunRequest | None = None,
    goal: str = Query(None),
):
    """Run one queue pass in the background using the saved or supplied goal."""
    requested_goal = (payload.goal if payload and payload.goal else goal) or None
    db = SessionLocal()
    try:
        settings_row = db.query(Settings).first()
        if requested_goal and settings_row:
            settings_row.goal = requested_goal
            db.commit()
        resolved_goal = requested_goal or (
            settings_row.goal if settings_row else app_settings.DEFAULT_GOAL
        )
    finally:
        db.close()

    from app.agents import QueueManager

    result = await QueueManager().process_queue()

    return {
        "message": "Queue run completed",
        "goal": resolved_goal,
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
if os.path.exists(frontend_dist):
    try:
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend-dist")
    except (RuntimeError, OSError):
        pass
elif os.path.exists(frontend_public):
    # Fallback to serving index.html from public (development mode)
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