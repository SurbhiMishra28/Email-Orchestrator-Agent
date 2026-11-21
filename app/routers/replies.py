"""Router for email reply processing and classification (tenant-scoped)."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.db import SessionLocal, Event, Contact, Log
from app.deps import current_tenant_id

router = APIRouter()


# Request/Response models
class ReplyAnalyzeRequest(BaseModel):
    subject: str
    body: str
    sender_email: str
    contact_id: Optional[int] = None


class ReplyAnalyzeResponse(BaseModel):
    reply_type: str
    confidence: float
    sentiment: str
    key_points: list
    suggested_action: str
    needs_human_review: bool
    contact_id: Optional[int] = None
    event_id: Optional[int] = None
    auto_schedule_draft_id: Optional[int] = None  # New field for auto-scheduling


class ReplyEventResponse(BaseModel):
    id: int
    contact_id: int
    event_type: str
    data: Dict[str, Any]
    timestamp: str


class ScheduleRequest(BaseModel):
    contact_id: int
    contact_email: str
    contact_name: str
    company: Optional[str] = ""
    preferred_days: Optional[List[str]] = None
    preferred_time: Optional[str] = "10:00 AM - 4:00 PM"
    duration_minutes: int = 10


@router.post("/analyze", response_model=ReplyAnalyzeResponse)
def analyze_reply(
    request: ReplyAnalyzeRequest,
    tenant_id: int = Depends(current_tenant_id),
):
    """Analyze and classify an incoming email reply.
    
    This endpoint takes an email reply (subject and body) and classifies it
    to determine the appropriate next action.
    
    - positive_response: Recipient is interested in engaging further
    - negative_response: Recipient is not interested or declining
    - question: Recipient has questions or is asking for more info
    - spam: Unsolicited or irrelevant content
    - no_reply_needed: Acknowledgment with no follow-up needed
    """
    from app.agents import ReplyAnalyzerAgent

    if request.contact_id is not None:
        db = SessionLocal()
        try:
            owned = (
                db.query(Contact.id)
                .filter(
                    Contact.id == request.contact_id,
                    Contact.tenant_id == tenant_id,
                )
                .first()
            )
        finally:
            db.close()
        if not owned:
            raise HTTPException(status_code=404, detail="Contact not found")

    try:
        agent = ReplyAnalyzerAgent(
            contact_id=request.contact_id,
            draft_id=None
        )
        
        result = agent.analyze_reply(
            subject=request.subject,
            body=request.body,
            sender_email=request.sender_email
        )
        
        agent.close()
        
        return ReplyAnalyzeResponse(**result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@router.get("/events/{contact_id}", response_model=list[ReplyEventResponse])
def get_reply_events(
    contact_id: int,
    limit: int = 50,
    tenant_id: int = Depends(current_tenant_id),
):
    """Get reply events for a specific contact.
    
    Returns a list of reply_received events for the given contact ID.
    """
    db = SessionLocal()
    try:
        contact = (
            db.query(Contact.id)
            .filter(Contact.id == contact_id, Contact.tenant_id == tenant_id)
            .first()
        )
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        events = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant_id,
                Event.contact_id == contact_id,
                Event.event_type == "reply_received"
            )
            .order_by(Event.timestamp.desc())
            .limit(limit)
            .all()
        )
        
        result = []
        for e in events:
            result.append({
                "id": e.id,
                "contact_id": e.contact_id,
                "event_type": e.event_type,
                "data": e.data,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None
            })
        
        return result
    
    finally:
        db.close()