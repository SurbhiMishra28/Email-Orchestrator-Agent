"""Drafts API router."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException

from app.db import SessionLocal, Contact, Draft, Log, SMTPConfig, Template
from app.models.schemas import DraftCreate, DraftUpdate, DraftOut
from app.agents import expand_template_with_ai
from app.services.limits import check_send_allowed
from app.services.mailer import (
    MailDeliveryError,
    MailNotConfigured,
    is_configured,
    send_email,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _mark_blocked(db, draft: Draft, reason: str) -> None:
    """Record why a draft could not be sent without pretending it went out."""
    draft.status = "blocked"
    draft.error_message = reason
    db.add(Log(message=f"Draft {draft.id} blocked: {reason}", level="warning"))
    db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=List[DraftOut])
def list_drafts(status: str = None, skip: int = 0, limit: int = 100):
    db = SessionLocal()
    try:
        query = db.query(Draft)
        if status:
            query = query.filter(Draft.status == status)
        drafts = query.offset(skip).limit(limit).all()
        return [DraftOut.model_validate(d) for d in drafts]
    finally:
        db.close()


@router.post("/compose", response_model=DraftOut)
def compose_draft(draft: DraftCreate):
    db = SessionLocal()
    try:
        # Verify contact exists
        contact = db.query(Contact).filter(Contact.id == draft.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        new_draft = Draft(
            contact_id=draft.contact_id,
            subject=draft.subject,
            body=draft.body,
            status="draft"
        )
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        
        log = Log(message=f"Draft created for contact {contact.email}", level="info")
        db.add(log)
        db.commit()
        
        return DraftOut.model_validate(new_draft)
    finally:
        db.close()


@router.get("/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int):
    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        return DraftOut.model_validate(draft)
    finally:
        db.close()


@router.post("/{draft_id}/update", response_model=DraftOut)
def update_draft(draft_id: int, draft: DraftUpdate):
    """Update a draft by ID."""
    db = SessionLocal()
    try:
        db_draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not db_draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        for field, value in draft.model_dump(exclude_unset=True).items():
            setattr(db_draft, field, value)
        
        db.commit()
        db.refresh(db_draft)
        return DraftOut.model_validate(db_draft)
    finally:
        db.close()


@router.post("/{draft_id}/redraft", response_model=DraftOut)
def redraft_draft(draft_id: int):
    """Regenerate a draft from an active template (AI-personalized when available)."""
    db = SessionLocal()
    try:
        db_draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not db_draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if db_draft.status in {"sent", "sending"}:
            raise HTTPException(
                status_code=409,
                detail="This draft has already been sent and cannot be redrafted.",
            )

        contact = db.query(Contact).filter(Contact.id == db_draft.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        template = (
            db.query(Template)
            .filter(Template.is_active == True, Template.category == "intro")
            .first()
        )
        if not template:
            template = db.query(Template).filter(Template.is_active == True).first()
        if not template:
            raise HTTPException(
                status_code=400,
                detail="No active template is available to redraft from.",
            )

        try:
            expanded = asyncio.run(expand_template_with_ai(template, contact))
        except Exception as exc:
            logger.warning("Redraft failed for draft %s: %s", draft_id, exc)
            raise HTTPException(status_code=502, detail=f"Redraft failed: {exc}") from exc

        db_draft.subject = expanded["subject"]
        db_draft.body = expanded["body"]
        db_draft.status = "draft"
        db_draft.error_message = None
        db.add(Log(message=f"Draft {draft_id} redrafted from template '{template.name}'", level="info"))
        db.commit()
        db.refresh(db_draft)
        return DraftOut.model_validate(db_draft)
    finally:
        db.close()


@router.post("/{draft_id}/send")
def send_draft(draft_id: int):
    """Send a draft email via the configured SMTP relay.

    A draft is only ever marked ``sent`` after the relay accepted the message.
    Missing settings or ineligible recipients leave it ``blocked`` with a reason.
    """
    db = SessionLocal()
    try:
        db_draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not db_draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if db_draft.status == "sent":
            return {"message": "Draft already sent", "status": "sent"}

        contact = db.query(Contact).filter(Contact.id == db_draft.contact_id).first()
        if not contact or not contact.email:
            raise HTTPException(status_code=404, detail="Recipient contact not found")

        if not contact.eligible_to_email:
            reason = (
                "Recipient is not marked eligible to email. "
                "Confirm permission in Contacts before sending."
            )
            _mark_blocked(db, db_draft, reason)
            raise HTTPException(status_code=409, detail=reason)

        smtp_config = db.query(SMTPConfig).first()
        if not is_configured(smtp_config):
            reason = (
                "SMTP is not configured. Add and test SMTP settings before sending."
            )
            _mark_blocked(db, db_draft, reason)
            raise HTTPException(status_code=409, detail=reason)

        allowed, limit_reason = check_send_allowed(db, contact)
        if not allowed:
            raise HTTPException(status_code=429, detail=limit_reason)

        # Atomically claim the draft so two concurrent requests cannot both send.
        claimed = (
            db.query(Draft)
            .filter(
                Draft.id == draft_id,
                Draft.status.in_(["draft", "blocked", "failed"]),
            )
            .update({Draft.status: "sending"}, synchronize_session=False)
        )
        db.commit()
        if not claimed:
            current = db.query(Draft).filter(Draft.id == draft_id).first()
            if current and current.status == "sent":
                return {"message": "Draft already sent", "status": "sent"}
            raise HTTPException(
                status_code=409, detail="This draft is already being sent."
            )
        db.refresh(db_draft)

        try:
            send_email(smtp_config, contact.email, db_draft.subject, db_draft.body)
        except MailNotConfigured as exc:
            _mark_blocked(db, db_draft, str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MailDeliveryError as exc:
            db_draft.status = "failed"
            db_draft.error_message = str(exc)
            db_draft.attempt_count = (db_draft.attempt_count or 0) + 1
            db.commit()
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        db_draft.status = "sent"
        db_draft.sent_at = datetime.now(timezone.utc)
        db_draft.error_message = None
        db_draft.attempt_count = (db_draft.attempt_count or 0) + 1
        db.add(Log(message=f"Draft {draft_id} sent to {contact.email}", level="info"))
        db.commit()
        return {"message": "Email sent successfully", "recipient": contact.email, "status": "sent"}
    finally:
        db.close()