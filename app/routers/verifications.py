"""Email verification API router."""
import threading
import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field

from app.db import SessionLocal, Contact, EmailVerification, VerificationJob, Log
from app.models.schemas import EmailVerificationOut
from app.services.verification import verify_email, verify_bulk, VerificationResult

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class SingleVerifyRequest(BaseModel):
    email: EmailStr
    contact_id: Optional[int] = None
    check_smtp: bool = True
    check_catch_all: bool = True


class BulkVerifyRequest(BaseModel):
    contact_ids: List[int] = Field(..., min_length=1)
    check_smtp: bool = True
    check_catch_all: bool = True


class JobStatusResponse(BaseModel):
    id: int
    status: str
    total: int
    processed: int
    deliverable: int
    undeliverable: int
    risky: int
    inconclusive: int
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class VerificationStats(BaseModel):
    total: int
    deliverable: int
    undeliverable: int
    risky: int
    inconclusive: int
    not_checked: int


def _result_to_model(result: VerificationResult, contact_id: Optional[int] = None) -> EmailVerification:
    """Convert VerificationResult to EmailVerification model."""
    return EmailVerification(
        email=result.email,
        contact_id=contact_id,
        status=result.status,
        smtp_check=result.smtp_check,
        mx_check=result.mx_check,
        catch_all=result.catch_all,
        disposable=result.disposable,
        domain=result.domain,
        last_checked=datetime.now(timezone.utc),
    )


def _run_bulk_verification(job_id: int, contact_ids: List[int], check_smtp: bool, check_catch_all: bool):
    """Background task to run bulk verification."""
    db = SessionLocal()
    try:
        # Get contacts
        contacts = db.query(Contact).filter(Contact.id.in_(contact_ids)).all()
        emails = [(c.email, c.id) for c in contacts]
        
        # Update job status to running
        job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
        if job:
            job.status = "running"
            job.total = len(emails)
            db.commit()
        
        def progress_callback(current: int, total: int, result: VerificationResult):
            job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
            if job:
                job.processed = current
                if result.status == "deliverable":
                    job.deliverable += 1
                elif result.status == "undeliverable":
                    job.undeliverable += 1
                elif result.status == "risky":
                    job.risky += 1
                elif result.status == "inconclusive":
                    job.inconclusive += 1
                db.commit()
        
        # Run verification
        results = verify_bulk(
            [e[0] for e in emails],
            check_smtp=check_smtp,
            check_catch_all=check_catch_all,
            progress_callback=progress_callback
        )
        
        # Save individual results
        for (email, contact_id), result in zip(emails, results):
            # Check if verification already exists
            existing = db.query(EmailVerification).filter(EmailVerification.email == email).first()
            if existing:
                existing.status = result.status
                existing.smtp_check = result.smtp_check
                existing.mx_check = result.mx_check
                existing.catch_all = result.catch_all
                existing.disposable = result.disposable
                existing.domain = result.domain
                existing.last_checked = datetime.now(timezone.utc)
                existing.contact_id = contact_id
            else:
                verification = _result_to_model(result, contact_id)
                db.add(verification)
            
            # Auto-update contact eligibility for undeliverable
            if result.status == "undeliverable" and contact_id:
                contact = db.query(Contact).filter(Contact.id == contact_id).first()
                if contact and contact.eligible_to_email:
                    contact.eligible_to_email = False
                    log = Log(message=f"Contact {contact_id} marked ineligible due to undeliverable email: {email}", level="warning")
                    db.add(log)
        
        # Update job completion
        job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
        if job:
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        
        # Log completion
        log = Log(message=f"Bulk verification job {job_id} completed: {len(results)} emails checked", level="info")
        db.add(log)
        db.commit()
        
    except Exception as e:
        logger.error(f"Bulk verification job {job_id} failed: {e}")
        job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@router.get("/stats", response_model=VerificationStats)
def get_verification_stats():
    """Get verification statistics."""
    db = SessionLocal()
    try:
        total = db.query(EmailVerification).count()
        deliverable = db.query(EmailVerification).filter(EmailVerification.status == "deliverable").count()
        undeliverable = db.query(EmailVerification).filter(EmailVerification.status == "undeliverable").count()
        risky = db.query(EmailVerification).filter(EmailVerification.status == "risky").count()
        inconclusive = db.query(EmailVerification).filter(EmailVerification.status == "inconclusive").count()
        not_checked = db.query(EmailVerification).filter(EmailVerification.status == "not_checked").count()
        
        return VerificationStats(
            total=total,
            deliverable=deliverable,
            undeliverable=undeliverable,
            risky=risky,
            inconclusive=inconclusive,
            not_checked=not_checked
        )
    finally:
        db.close()


@router.post("/check", response_model=EmailVerificationOut)
def check_single_email(request: SingleVerifyRequest):
    """Verify a single email address."""
    db = SessionLocal()
    try:
        result = verify_email(request.email, request.check_smtp, request.check_catch_all)
        
        # Save or update verification record
        existing = db.query(EmailVerification).filter(EmailVerification.email == request.email).first()
        if existing:
            existing.status = result.status
            existing.smtp_check = result.smtp_check
            existing.mx_check = result.mx_check
            existing.catch_all = result.catch_all
            existing.disposable = result.disposable
            existing.domain = result.domain
            existing.last_checked = datetime.now(timezone.utc)
            if request.contact_id:
                existing.contact_id = request.contact_id
            db.commit()
            db.refresh(existing)
            return existing
        else:
            verification = _result_to_model(result, request.contact_id)
            db.add(verification)
            db.commit()
            db.refresh(verification)
            return verification
    finally:
        db.close()


@router.post("/bulk", response_model=JobStatusResponse)
def start_bulk_verification(request: BulkVerifyRequest, background_tasks: BackgroundTasks):
    """Start a bulk verification job for selected contacts."""
    db = SessionLocal()
    try:
        # Validate contacts exist
        contacts = db.query(Contact).filter(Contact.id.in_(request.contact_ids)).all()
        if len(contacts) != len(request.contact_ids):
            found_ids = {c.id for c in contacts}
            missing = [cid for cid in request.contact_ids if cid not in found_ids]
            raise HTTPException(status_code=404, detail=f"Contacts not found: {missing}")
        
        # Create job record
        job = VerificationJob(
            status="pending",
            total=len(contacts),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Start background task
        background_tasks.add_task(
            _run_bulk_verification,
            job.id,
            request.contact_ids,
            request.check_smtp,
            request.check_catch_all
        )
        
        return JobStatusResponse(
            id=job.id,
            status=job.status,
            total=job.total,
            processed=job.processed,
            deliverable=job.deliverable,
            undeliverable=job.undeliverable,
            risky=job.risky,
            inconclusive=job.inconclusive,
            created_at=job.created_at.isoformat() if job.created_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=job.error
        )
    finally:
        db.close()


@router.get("/bulk/{job_id}", response_model=JobStatusResponse)
def get_bulk_job_status(job_id: int):
    """Get bulk verification job status."""
    db = SessionLocal()
    try:
        job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return JobStatusResponse(
            id=job.id,
            status=job.status,
            total=job.total,
            processed=job.processed,
            deliverable=job.deliverable,
            undeliverable=job.undeliverable,
            risky=job.risky,
            inconclusive=job.inconclusive,
            created_at=job.created_at.isoformat() if job.created_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=job.error
        )
    finally:
        db.close()


@router.get("", response_model=List[EmailVerificationOut])
def list_verifications(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = Query(None, pattern="^(deliverable|undeliverable|risky|inconclusive|not_checked)$"),
    domain: Optional[str] = None,
):
    """List email verifications with optional filters."""
    db = SessionLocal()
    try:
        query = db.query(EmailVerification)
        
        if status:
            query = query.filter(EmailVerification.status == status)
        if domain:
            query = query.filter(EmailVerification.domain.ilike(f"%{domain}%"))
        
        # DESC places NULLs last on MySQL/MariaDB and SQLite, so no NULLS LAST clause
        verifications = query.order_by(EmailVerification.last_checked.desc()).offset(skip).limit(limit).all()
        return verifications
    finally:
        db.close()


@router.get("/{verification_id}", response_model=EmailVerificationOut)
def get_verification(verification_id: int):
    """Get a single verification by ID."""
    db = SessionLocal()
    try:
        verification = db.query(EmailVerification).filter(EmailVerification.id == verification_id).first()
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        return verification
    finally:
        db.close()


@router.delete("/{verification_id}")
def delete_verification(verification_id: int):
    """Delete a verification record."""
    db = SessionLocal()
    try:
        verification = db.query(EmailVerification).filter(EmailVerification.id == verification_id).first()
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        
        db.delete(verification)
        db.commit()
        return {"message": "Verification deleted"}
    finally:
        db.close()


@router.post("/{verification_id}/reverify", response_model=EmailVerificationOut)
def reverify_email(verification_id: int, check_smtp: bool = True, check_catch_all: bool = True):
    """Re-verify an email address."""
    db = SessionLocal()
    try:
        verification = db.query(EmailVerification).filter(EmailVerification.id == verification_id).first()
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        
        result = verify_email(verification.email, check_smtp, check_catch_all)
        
        verification.status = result.status
        verification.smtp_check = result.smtp_check
        verification.mx_check = result.mx_check
        verification.catch_all = result.catch_all
        verification.disposable = result.disposable
        verification.domain = result.domain
        verification.last_checked = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(verification)
        return verification
    finally:
        db.close()