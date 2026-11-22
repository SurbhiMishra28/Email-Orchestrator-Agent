"""Agents API router - exposes subagents via REST API (tenant-scoped)."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from pydantic import BaseModel
from sqlalchemy import func

logger = logging.getLogger(__name__)

from app.config import settings as app_settings
from app.db import SessionLocal, Contact, Template, Draft, SMTPConfig, Settings, Log
from app.deps import current_tenant_id
from app.services.limits import check_tenant_send_allowed
from app.services.mailer import (
    MailDeliveryError,
    MailNotConfigured,
    send_email,
)
from app.services.usage import EMAILS_SENT, record_usage
from app.services.recipients import blocked_reason
from app.agents import (
    PersonalizedEmailAgent,
    SenderAgent,
    CalendarAgent,
    AIBrainAgent,
    ReplyAnalyzerAgent,
    AutoResponder,
    QueueManager,
)

router = APIRouter()


def _tenant_contact(db, contact_id: int, tenant_id: int) -> Contact:
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.tenant_id == tenant_id)
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    return contact


def _tenant_smtp(db, tenant_id: int):
    return (
        db.query(SMTPConfig).filter(SMTPConfig.tenant_id == tenant_id).first()
    )


def _tenant_settings(db, tenant_id: int):
    return db.query(Settings).filter(Settings.tenant_id == tenant_id).first()


# ============================================================================
# PERSONALIZED EMAIL ENDPOINTS
# ============================================================================

class PersonalizeRequest(BaseModel):
    """Request model for personalization endpoint."""
    contact_id: int
    template_id: int
    use_ai: bool = True
    custom_values: Optional[Dict[str, Any]] = None


@router.post("/personalize")
async def personalize_email(
    request: PersonalizeRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Generate personalized email content for a contact using a template.
    
    This endpoint uses the PersonalizedEmailAgent to generate
    fully personalized email content with optional AI enhancement.
    """
    db = SessionLocal()
    try:
        # Get contact
        contact = _tenant_contact(db, request.contact_id, tenant_id)
        
        if not contact.eligible_to_email:
            raise HTTPException(
                status_code=400, 
                detail=f"Contact {request.contact_id} is not eligible for email"
            )
        
        # Get template
        template = (
            db.query(Template)
            .filter(
                Template.id == request.template_id,
                Template.tenant_id == tenant_id,
                Template.is_active == True,
            )
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail=f"Template {request.template_id} not found or inactive")
        
        # Use PersonalizedEmailAgent
        agent = PersonalizedEmailAgent(
            contact_id=request.contact_id,
            template_id=request.template_id
        )
        
        result = agent.personalize(use_ai=request.use_ai)
        agent.close()
        
        return {
            "subject": result["subject"],
            "body": result["body"],
            "contact_id": request.contact_id,
            "template_id": request.template_id,
            "eligible": contact.eligible_to_email
        }
    finally:
        db.close()


# ============================================================================
# SENDER ENDPOINTS
# ============================================================================

class SendEmailRequest(BaseModel):
    """Request model for sending email."""
    to_email: str
    subject: str
    body: str
    from_name: Optional[str] = None
    from_email: Optional[str] = None


@router.post("/send")
async def send_email_endpoint(
    request: SendEmailRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Send one email now, through the same limits as the queue.

    The recipient must already be a contact of the caller's tenant: that is what
    makes the daily cap, domain cap and pacing counter apply to this send, and
    what lets the message appear in drafts and analytics.
    """
    db = SessionLocal()
    try:
        smtp_config = _tenant_smtp(db, tenant_id)

        agent = SenderAgent(smtp_config=smtp_config)

        # Check if configured
        if not agent.is_configured():
            raise HTTPException(
                status_code=503,
                detail="SMTP is not configured. Please configure SMTP settings first."
            )

        recipient = (request.to_email or "").strip().lower()
        contact = (
            db.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                func.lower(Contact.email) == recipient,
            )
            .first()
        )
        if not contact:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"{request.to_email} is not a contact of this workspace. "
                    "Add it as a contact first so the send is metered and tracked."
                ),
            )
        if not contact.eligible_to_email:
            raise HTTPException(
                status_code=400,
                detail=f"Contact {request.to_email} is not eligible for email",
            )
        if contact.email_blacklisted:
            raise HTTPException(
                status_code=400,
                detail=f"Contact {request.to_email} is blacklisted after a bounce",
            )

        problem = blocked_reason(recipient, getattr(smtp_config, "sender", None))
        if problem:
            raise HTTPException(status_code=422, detail=problem)

        allowed, reason = check_tenant_send_allowed(db, tenant_id, recipient)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)

        draft = Draft(
            contact_id=contact.id,
            tenant_id=tenant_id,
            subject=request.subject,
            body=request.body,
            status="sending",
            variables={"message_kind": "direct_send"},
            attempt_count=1,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        try:
            msg_id = await asyncio.to_thread(
                send_email,
                smtp_config,
                recipient,
                request.subject,
                request.body,
                request.from_name,
                request.from_email,
                None,
            )
        except MailNotConfigured as exc:
            draft.status = "failed"
            draft.error_message = str(exc)
            db.commit()
            raise HTTPException(status_code=503, detail=f"SMTP not configured: {exc}")
        except MailDeliveryError as exc:
            draft.status = "failed"
            draft.error_message = str(exc)
            db.commit()
            raise HTTPException(status_code=400, detail=f"Send failed: {exc}")

        draft.status = "sent"
        draft.sent_at = datetime.now(timezone.utc)
        draft.error_message = None
        record_usage(db, tenant_id, EMAILS_SENT)
        db.commit()

        return {
            "success": True,
            "message": "Email sent successfully",
            "message_id": msg_id,
            "recipient": request.to_email,
            "draft_id": draft.id,
        }
    finally:
        db.close()


@router.get("/test-smtp")
def test_smtp_connection(tenant_id: int = Depends(current_tenant_id)):
    """Test SMTP connection using SenderAgent."""
    db = SessionLocal()
    try:
        smtp_config = _tenant_smtp(db, tenant_id)
        agent = SenderAgent(smtp_config=smtp_config)
        
        success, message = agent.test_connection()
        
        result = {
            "success": success,
            "message": message,
            "configured": agent.is_configured(),
        }
        if smtp_config:
            result["host"] = smtp_config.host
            result["port"] = smtp_config.port
        return result
    finally:
        db.close()


# ============================================================================
# CALENDAR ENDPOINTS
# ============================================================================

class CalendarEventRequest(BaseModel):
    """Request model for creating calendar events."""
    summary: str
    start_time: str
    duration_minutes: int = 30
    attendees: Optional[List[str]] = None
    description: Optional[str] = None
    location: Optional[str] = None
    provider: str = "manual"


@router.get("/calendar")
def list_calendars(
    provider: str = Query("manual", description="Calendar provider"),
    tenant_id: int = Depends(current_tenant_id),
):
    """List available calendars."""
    db = SessionLocal()
    try:
        settings_row = _tenant_settings(db, tenant_id)
        agent = CalendarAgent(
            provider=provider,
            booking_url=settings_row.calendly_url if settings_row else None,
        )
    finally:
        db.close()
    
    if not agent.available():
        raise HTTPException(
            status_code=501,
            detail=f"Calendar provider '{provider}' not available"
        )
    
    calendars = agent.list_calendars()
    return {"calendars": calendars, "provider": provider}


@router.post("/calendar/event")
def create_calendar_event(
    request: CalendarEventRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Create a calendar event.
    
    Args:
        summary: Event title
        start_time: ISO format start datetime (e.g., "2024-01-15T14:00:00Z")
        duration_minutes: Event duration
        attendees: List of attendee emails
        description: Event description
        location: Physical or virtual location
        provider: Calendar provider
    """
    from datetime import datetime
    
    try:
        start_dt = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start_time format. Use ISO format.")

    if request.provider.lower() == "calendly":
        raise HTTPException(
            status_code=501,
            detail="Calendly events are created when invitees book through the configured Calendly link.",
        )
    
    agent = CalendarAgent(provider=request.provider)
    
    if not agent.available():
        raise HTTPException(
            status_code=501,
            detail=f"Calendar provider '{request.provider}' not available"
        )
    
    event = agent.create_event(
        summary=request.summary,
        start_time=start_dt,
        duration_minutes=request.duration_minutes,
        attendees=request.attendees or [],
        description=request.description,
        location=request.location
    )
    
    return {
        "event": event,
        "meeting_link": agent.generate_meeting_link("call")
    }


# ============================================================================
# AI BRAIN ENDPOINTS
# ============================================================================

class EnhanceSubjectRequest(BaseModel):
    """Request model for subject enhancement."""
    subject: str
    context: Optional[Dict[str, Any]] = None


class EnhanceBodyRequest(BaseModel):
    """Request model for body enhancement."""
    body: str
    style: str = "professional"


class GenerateAlternativesRequest(BaseModel):
    """Request model for generating alternatives."""
    subject: str
    body: str
    count: int = 3


class SummarizeThreadRequest(BaseModel):
    """Request model for thread summarization."""
    messages: Optional[List[str]] = None


class ExtractActionItemsRequest(BaseModel):
    """Request model for action item extraction."""
    email_text: str


@router.post("/brain/enhance-subject")
def enhance_subject(
    request: EnhanceSubjectRequest = Body(...),
    tenant_id: int = Depends(current_tenant_id),
):
    """Enhance an email subject line using AI.
    
    Returns an optimized subject line that's more engaging and concise.
    """
    agent = AIBrainAgent()
    optimized = agent.enhance_subject(request.subject, request.context)
    
    return {
        "original": request.subject,
        "enhanced": optimized
    }


@router.post("/brain/enhance-body")
def enhance_body(
    request: EnhanceBodyRequest = Body(...),
    tenant_id: int = Depends(current_tenant_id),
):
    """Enhance email body content using AI.
    
    Improves clarity, tone, and persuasiveness while maintaining the message.
    """
    agent = AIBrainAgent()
    enhanced = agent.enhance_body(request.body, request.style)
    
    return {
        "original": request.body,
        "enhanced": enhanced
    }


@router.post("/brain/alternatives")
def generate_alternatives(
    request: GenerateAlternativesRequest = Body(...),
    tenant_id: int = Depends(current_tenant_id),
):
    """Generate alternative subject/body combinations for A/B testing."""
    agent = AIBrainAgent()
    alternatives = agent.generate_alternatives(request.subject, request.body, request.count)
    
    return {
        "original": {"subject": request.subject, "body": request.body},
        "alternatives": alternatives
    }


@router.post("/brain/summarize")
def summarize_thread(
    request: SummarizeThreadRequest = Body(...),
    tenant_id: int = Depends(current_tenant_id),
):
    """Summarize an email thread.
    
    Pass messages as a JSON-encoded array in the 'messages' field of the request body.
    """
    if not request.messages or len(request.messages) == 0:
        raise HTTPException(status_code=400, detail="At least one message required")
    
    agent = AIBrainAgent()
    summary = agent.summarize_thread(request.messages)
    
    return {"summary": summary, "messages_analyzed": len(request.messages)}


@router.post("/brain/action-items")
def extract_action_items(
    request: ExtractActionItemsRequest = Body(...),
    tenant_id: int = Depends(current_tenant_id),
):
    """Extract actionable items from email text."""
    agent = AIBrainAgent()
    items = agent.extract_action_items(request.email_text)
    
    return {
        "email_preview": request.email_text[:200] + "..." if len(request.email_text) > 200 else request.email_text,
        "action_items": items
    }


# ============================================================================
# UTILITY ENDPOINT
# ============================================================================

@router.get("/status")
def get_agents_status(tenant_id: int = Depends(current_tenant_id)):
    """Get status of all agents."""
    db = SessionLocal()
    try:
        smtp_config = _tenant_smtp(db, tenant_id)
        settings_row = _tenant_settings(db, tenant_id)
        
        sender_agent = SenderAgent(smtp_config=smtp_config)
        calendar_agent = CalendarAgent(
            provider="calendly",
            booking_url=settings_row.calendly_url if settings_row else None,
        )
        ai_brain_agent = AIBrainAgent()
        
        return {
            "personalized_email": {
                "status": "available",
                "description": "Generates personalized email content per contact"
            },
            "sender": {
                "status": "configured" if sender_agent.is_configured() else "not_configured",
                "description": "Handles SMTP email delivery"
            },
            "calendar": {
                "status": "configured" if calendar_agent.available() else "not_configured",
                "provider": calendar_agent.provider,
                "description": "Calendly booking link"
            },
            "ai_brain": {
                "status": "enabled" if app_settings.NVIDIA_API_KEY else "disabled",
                "model": getattr(app_settings, 'NVIDIA_MODEL', 'nvidia/nllama-3-70b'),
                "description": "AI-powered content optimization"
            },
            "reply_analyzer": {
                "status": "available",
                "description": "Classifies incoming email replies"
            },
            "auto_responder": {
                "status": "configured" if sender_agent.is_configured() else "not_configured",
                "description": "Automatically sends replies to classified responses"
            }
        }
    finally:
        db.close()


# ============================================================================
# AUTO-RESPONSE ENDPOINT
# ============================================================================

class AutoReplyRequest(BaseModel):
    """Request model for auto-reply endpoint."""
    contact_id: int
    classification: Dict[str, Any]  # From ReplyAnalyzerAgent
    original_subject: str
    original_body: str
    sender_email: str
    send_calendar_invite: bool = False


class AutoReplyResponse(BaseModel):
    """Response model for auto-reply endpoint."""
    success: bool
    message: str
    reply_type: str
    response_subject: Optional[str] = None
    response_body_preview: Optional[str] = None
    calendar_event_id: Optional[str] = None
    needs_human_review: bool = False


@router.post("/auto-reply")
def auto_reply(
    request: AutoReplyRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Generate and send an automatic reply based on response classification.
    
    This endpoint takes a classified reply and generates an appropriate
    auto-response based on the reply type.
    
    - positive_response: Sends a meeting proposal
    - question: Sends a detailed response with follow-up
    - schedule_call: Sends calendar invite
    - negative_response: No auto-reply (respects preference)
    - spam: No action
    - no_reply_needed: No action
    
    Args:
        request: AutoReplyRequest with contact info, classification, and original email
        
    Returns:
        AutoReplyResponse with send status and details
    """
    db = SessionLocal()
    try:
        # Get contact
        contact = _tenant_contact(db, request.contact_id, tenant_id)
        
        if not contact.eligible_to_email:
            raise HTTPException(
                status_code=400, 
                detail=f"Contact {request.contact_id} is not eligible for email"
            )
        
        # Get SMTP config
        smtp_config = _tenant_smtp(db, tenant_id)
        
        # Initialize auto-responder
        auto_responder = AutoResponder(
            contact_id=request.contact_id,
            smtp_config=smtp_config
        )
        
        # Generate response
        response = auto_responder.generate_response(
            classification=request.classification,
            original_subject=request.original_subject,
            original_body=request.original_body,
            sender_email=request.sender_email
        )
        
        if not response:
            return AutoReplyResponse(
                success=False,
                message=f"No auto-response generated for reply_type: {request.classification.get('reply_type')}",
                reply_type=request.classification.get('reply_type', 'unknown')
            )
        
        # Check if calendar invite is needed
        calendar_event_id = None
        if request.send_calendar_invite or request.classification.get('suggested_action') == 'schedule_call':
            try:
                calendar_event = auto_responder.calendar_agent.create_event(
                    summary=f"Call with {contact.name or 'Prospect'}",
                    start_time=datetime.now(timezone.utc) + timedelta(days=2),
                    duration_minutes=30,
                    attendees=[request.sender_email],
                    description=f"Discussion about {request.original_subject}"
                )
                calendar_event_id = calendar_event.get('id', 'virtual_meeting')
                response['body'] += f"\n\nBook a meeting: {auto_responder._generate_calendar_link()}"
            except Exception as e:
                logger.warning(f"Calendar event creation failed: {e}")
        
        # Send response
        if not request.classification.get('needs_human_review', False):
            send_result = auto_responder.send_response(response)
            
            # Log the interaction
            auto_responder.log_interaction(
                event_id=request.classification.get('event_id', 0),
                send_result=send_result
            )
            
            return AutoReplyResponse(
                success=send_result.get('success', False),
                message=send_result.get('message', 'Unknown'),
                reply_type=response['reply_type'],
                response_subject=response.get('subject'),
                response_body_preview=response.get('body', '')[:200] if response.get('body') else None,
                calendar_event_id=calendar_event_id,
                needs_human_review=request.classification.get('needs_human_review', False)
            )
        else:
            return AutoReplyResponse(
                success=True,
                message="Response marked for human review",
                reply_type=response['reply_type'],
                response_subject=response.get('subject'),
                response_body_preview=response.get('body', '')[:200] if response.get('body') else None,
                needs_human_review=True
            )
    
    finally:
        db.close()
