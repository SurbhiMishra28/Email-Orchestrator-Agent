"""Agents API router - exposes subagents via REST API."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.config import settings as app_settings
from app.db import SessionLocal, Contact, Template, Draft, SMTPConfig, Settings, Log
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
    request: PersonalizeRequest
):
    """Generate personalized email content for a contact using a template.
    
    This endpoint uses the PersonalizedEmailAgent to generate
    fully personalized email content with optional AI enhancement.
    """
    db = SessionLocal()
    try:
        # Get contact
        contact = db.query(Contact).filter(Contact.id == request.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail=f"Contact {request.contact_id} not found")
        
        if not contact.eligible_to_email:
            raise HTTPException(
                status_code=400, 
                detail=f"Contact {request.contact_id} is not eligible for email"
            )
        
        # Get template
        template = db.query(Template).filter(
            Template.id == request.template_id,
            Template.is_active == True
        ).first()
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
    request: SendEmailRequest
):
    """Send an email directly using the SenderAgent.
    
    This endpoint bypasses draft creation and sends immediately.
    Useful for alerts, notifications, and one-off emails.
    """
    db = SessionLocal()
    try:
        smtp_config = db.query(SMTPConfig).first()
        
        agent = SenderAgent(smtp_config=smtp_config)
        
        # Check if configured
        if not agent.is_configured():
            raise HTTPException(
                status_code=503,
                detail="SMTP is not configured. Please configure SMTP settings first."
            )
        
        # Send email
        success, message, msg_id = agent.send(
            to_email=request.to_email,
            subject=request.subject,
            body=request.body,
            from_name=request.from_name,
            from_email=request.from_email
        )
        
        if success:
            return {
                "success": True,
                "message": "Email sent successfully",
                "message_id": msg_id,
                "recipient": request.to_email
            }
        else:
            raise HTTPException(status_code=400, detail=f"Send failed: {message}")
    finally:
        db.close()


@router.get("/test-smtp")
def test_smtp_connection():
    """Test SMTP connection using SenderAgent."""
    db = SessionLocal()
    try:
        smtp_config = db.query(SMTPConfig).first()
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
def list_calendars(provider: str = Query("manual", description="Calendar provider")):
    """List available calendars."""
    agent = CalendarAgent(provider=provider)
    
    if not agent.available():
        raise HTTPException(
            status_code=501,
            detail=f"Calendar provider '{provider}' not available"
        )
    
    calendars = agent.list_calendars()
    return {"calendars": calendars, "provider": provider}


@router.post("/calendar/event")
def create_calendar_event(
    request: CalendarEventRequest
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
    request: EnhanceSubjectRequest = Body(...)
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
    request: EnhanceBodyRequest = Body(...)
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
    request: GenerateAlternativesRequest = Body(...)
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
    request: SummarizeThreadRequest = Body(...)
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
    request: ExtractActionItemsRequest = Body(...)
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
def get_agents_status():
    """Get status of all agents."""
    db = SessionLocal()
    try:
        smtp_config = db.query(SMTPConfig).first()
        settings = db.query(Settings).first()
        
        sender_agent = SenderAgent(smtp_config=smtp_config)
        calendar_agent = CalendarAgent()
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
                "status": "available" if calendar_agent.available() else "limited",
                "provider": calendar_agent.provider,
                "description": "Meeting scheduling integration"
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
def auto_reply(request: AutoReplyRequest):
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
        contact = db.query(Contact).filter(Contact.id == request.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail=f"Contact {request.contact_id} not found")
        
        if not contact.eligible_to_email:
            raise HTTPException(
                status_code=400, 
                detail=f"Contact {request.contact_id} is not eligible for email"
            )
        
        # Get SMTP config
        smtp_config = db.query(SMTPConfig).first()
        
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