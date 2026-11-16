"""Router for email reply processing and classification."""
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.db import SessionLocal, Event, Contact, Log

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


class ReplyEventResponse(BaseModel):
    id: int
    contact_id: int
    event_type: str
    data: Dict[str, Any]
    timestamp: str


@router.post("/analyze", response_model=ReplyAnalyzeResponse)
def analyze_reply(request: ReplyAnalyzeRequest):
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
def get_reply_events(contact_id: int, limit: int = 50):
    """Get reply events for a specific contact.
    
    Returns a list of reply_received events for the given contact ID.
    """
    from app.db import SessionLocal, Event
    
    db = SessionLocal()
    try:
        events = (
            db.query(Event)
            .filter(
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