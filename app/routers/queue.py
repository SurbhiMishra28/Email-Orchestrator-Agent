"""Queue status API router."""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Body

from pydantic import BaseModel

from app.agents import QueueManager, expand_template_with_ai
from app.config import settings as app_settings
from app.db import Contact, Draft, Log, SessionLocal, Settings, Template

logger = logging.getLogger(__name__)

router = APIRouter()


# Request body model for run-all endpoint
class RunAllRequest(BaseModel):
    template_id: Optional[int] = None
    contact_ids: Optional[List[int]] = None


# Queue manager singleton
def get_queue_manager() -> QueueManager:
    """Get or create the singleton QueueManager instance."""
    if not hasattr(get_queue_manager, "_instance"):
        get_queue_manager._instance = QueueManager()
    return get_queue_manager._instance


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/status")
def get_queue_status():
    """Get current queue and scheduler status."""
    db = SessionLocal()
    qm = get_queue_manager()
    try:
        pending = (
            db.query(Draft)
            .filter(Draft.status.in_(["draft", "blocked"]))
            .count()
        )

        try:
            # Imported lazily so the router does not depend on startup order.
            from app.main import scheduler
            alive = bool(scheduler.running)
        except Exception:
            alive = qm.alive

        return {
            "scheduler": {
                "alive": alive,
                "last_poll": qm.last_poll
            },
            "pending_drafts": pending
        }
    finally:
        db.close()


@router.post("/followups")
async def run_followups():
    """Create any due follow-up drafts now (never sends them)."""
    from app.services.followups import generate_followups

    result = await generate_followups()
    return {"message": "Follow-up pass completed", **result}


@router.post("/run")
async def run_orchestration(goal: str = None):
    """Run one queue pass and return what happened."""
    db = SessionLocal()
    qm = get_queue_manager()
    try:
        if not goal:
            settings = db.query(Settings).first()
            goal = settings.goal if settings else app_settings.DEFAULT_GOAL

        result = await qm.process_queue()

        db.add(Log(message=f"Orchestration run: goal={goal}", level="info"))
        db.commit()

        return {"message": "Orchestration run completed", "goal": goal, "result": result}
    finally:
        db.close()


@router.post("/run-all")
async def run_orchestration_all(request: RunAllRequest = None, goal: str = None, template_id: int = None):
    """
    Create drafts for eligible contacts and process the queue.
    
    This endpoint:
    1. Finds all contacts with eligible_to_email=true (or specific contact_ids if provided)
    2. Creates a personalized draft for each using the specified or default template
    3. Processes the queue to send all drafts
    
    Returns details of drafts created and sent.
    
    If contact_ids is provided in the request body, only those contacts will be processed.
    """
    if request is None:
        request = RunAllRequest()
    
    # Use template_id from body if provided, otherwise from query param or default
    template_id = request.template_id or template_id
    contact_ids = request.contact_ids
    db = SessionLocal()
    qm = get_queue_manager()
    try:
        if not goal:
            settings = db.query(Settings).first()
            goal = settings.goal if settings else app_settings.DEFAULT_GOAL

        # Get template - use specified or first active template
        if template_id:
            template = db.query(Template).filter(Template.id == template_id, Template.is_active == True).first()
            if not template:
                raise HTTPException(status_code=404, detail=f"Template {template_id} not found or inactive")
        else:
            template = db.query(Template).filter(Template.is_active == True).first()
            if not template:
                raise HTTPException(status_code=404, detail="No active template found")

        # Get contacts - either specific IDs or all eligible
        if contact_ids:
            contacts = db.query(Contact).filter(Contact.id.in_(contact_ids), Contact.eligible_to_email == True).all()
            found_ids = {c.id for c in contacts}
            missing = [cid for cid in contact_ids if cid not in found_ids]
            if missing:
                logger.warning(f"Some contact IDs not found or not eligible: {missing}")
        else:
            contacts = db.query(Contact).filter(Contact.eligible_to_email == True).all()
        
        if not contacts:
            return {
                "message": "No eligible contacts found",
                "goal": goal,
                "drafts_created": 0,
                "result": {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []}
            }

        # Create drafts for each contact
        drafts_created = 0
        for contact in contacts:
            # Check if there's already a pending draft for this contact
            existing_draft = db.query(Draft).filter(
                Draft.contact_id == contact.id,
                Draft.status.in_(["draft", "blocked"])
            ).first()
            
            if existing_draft:
                # Skip if draft already exists
                continue
            
            # Create personalized draft
            try:
                expanded = await expand_template_with_ai(template, contact)
                draft = Draft(
                    contact_id=contact.id,
                    subject=expanded["subject"],
                    body=expanded["body"],
                    status="draft"
                )
                db.add(draft)
                drafts_created += 1
            except Exception as e:
                logger.warning(f"Failed to create draft for contact {contact.id}: {e}")
                continue
        
        db.commit()
        
        if drafts_created == 0:
            return {
                "message": "All eligible contacts already have pending drafts",
                "goal": goal,
                "drafts_created": 0,
                "result": {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []}
            }

        # Process the queue
        result = await qm.process_queue()

        db.add(Log(message=f"Orchestration run-all: goal={goal}, drafts_created={drafts_created}", level="info"))
        db.commit()

        return {
            "message": "Orchestration run-all completed",
            "goal": goal,
            "template_used": template.name,
            "drafts_created": drafts_created,
            "result": result
        }
    finally:
        db.close()