"""Tenant-scoped queue control API router."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body

from pydantic import BaseModel

from app.agents import QueueManager, expand_template_with_ai
from app.config import settings as app_settings
from app.db import Contact, Draft, Log, SessionLocal, Settings, Template
from app.deps import current_tenant_id
from app.services.recipients import blocked_reason
from app.services.usage import EMAILS_DRAFTED, record_usage

logger = logging.getLogger(__name__)

router = APIRouter()


# Budget for the synchronous drain in ``/run-all``. Once a send has just
# happened the pacing rule pauses the next one, and waiting that out would hold
# the HTTP request open; anything still queued is handed to the background
# worker instead, so a click never costs a 60-second wait.
SYNC_DRAIN_SECONDS = 25


# Request body model for run-all endpoint
class RunAllRequest(BaseModel):
    template_id: Optional[int] = None
    contact_ids: Optional[List[int]] = None
    list_id: Optional[int] = None
    campaign_id: Optional[int] = None


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
def get_queue_status(tenant_id: int = Depends(current_tenant_id)):
    """Get current queue and scheduler status."""
    db = SessionLocal()
    qm = get_queue_manager()
    try:
        pending = (
            db.query(Draft)
            .filter(
                Draft.tenant_id == tenant_id,
                Draft.status.in_(["draft", "blocked"]),
            )
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
async def run_followups(tenant_id: int = Depends(current_tenant_id)):
    """Create any due follow-up drafts now (never sends them)."""
    from app.services.followups import generate_followups

    result = await generate_followups(tenant_id=tenant_id)
    return {"message": "Follow-up pass completed", **result}


@router.post("/run")
async def run_orchestration(
    goal: str = None,
    tenant_id: int = Depends(current_tenant_id),
):
    """Run one queue pass for the caller's tenant and return what happened."""
    db = SessionLocal()
    qm = get_queue_manager()
    try:
        if not goal:
            settings = (
                db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
            )
            goal = settings.goal if settings else app_settings.DEFAULT_GOAL

        result = await qm.process_queue(tenant_id=tenant_id)

        db.add(
            Log(
                message=f"Orchestration run: goal={goal}",
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()

        return {"message": "Orchestration run completed", "goal": goal, "result": result}
    finally:
        db.close()


@router.post("/run-all")
async def run_orchestration_all(
    request: RunAllRequest = None,
    goal: str = None,
    template_id: int = None,
    tenant_id: int = Depends(current_tenant_id),
):
    """
    Create drafts for the tenant's eligible contacts and process the queue.
    
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
    list_id = request.list_id
    campaign = None
    db = SessionLocal()
    try:
        # A campaign run takes its template, list and subject from the campaign
        # row, so the listing's "send" action cannot drift from its settings.
        campaign = None
        if request.campaign_id is not None:
            campaign = _load_campaign(db, tenant_id, request.campaign_id)
            template_id = template_id or campaign.template_id
            list_id = campaign.list_id if campaign.list_id is not None else list_id
        if not goal:
            settings = (
                db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
            )
            goal = settings.goal if settings else app_settings.DEFAULT_GOAL

        template = _resolve_template(db, tenant_id, template_id)
        contacts = _select_contacts(db, tenant_id, contact_ids, list_id)

        if not contacts:
            return {
                "message": "No eligible contacts found",
                "goal": goal,
                "drafts_created": 0,
                "result": {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []}
            }

        drafts_created = await _create_drafts(
            db, tenant_id, template, contacts, campaign=campaign
        )
        db.commit()

        if drafts_created == 0:
            return {
                "message": "All eligible contacts already have pending drafts",
                "goal": goal,
                "drafts_created": 0,
                "result": {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []}
            }

        # Drain rather than a single pass: one pass stops at the 60-second
        # pacing rule, which would deliver one email per click. The drain is
        # bounded so the request still returns; anything left is handed to the
        # background worker instead of silently waiting for another click.
        from app.services.send_worker import drain_queue, get_worker

        if app_settings.ENABLE_BACKGROUND_JOBS:
            result = await drain_queue(
                tenant_id=tenant_id, max_seconds=SYNC_DRAIN_SECONDS
            )
        else:
            # No background worker exists on this host (serverless), so a
            # handoff would drop the remaining sends. Finish them inline and
            # let the function timeout be the only bound.
            result = await drain_queue(tenant_id=tenant_id)

        # Only this batch matters here: a draft left over from an older run must
        # not be reported as "queued" by a selection-scoped send.
        selected_ids = [contact.id for contact in contacts]
        remaining = (
            db.query(Draft)
            .filter(
                Draft.tenant_id == tenant_id,
                Draft.status.in_(["draft", "blocked"]),
                Draft.contact_id.in_(selected_ids),
            )
            .count()
        )
        job_id = None
        if remaining and app_settings.ENABLE_BACKGROUND_JOBS:
            job_id = get_worker().submit(tenant_id).id
            result["queued"] = True
            result["job_id"] = job_id
            result["remaining"] = remaining
        elif remaining:
            result["remaining"] = remaining
            result["paused"] = True

        if campaign is not None:
            # The campaign row is the listing's source of truth: mark it sent
            # and record the audience it went to.
            campaign.status = "sent"
            campaign.sent_at = datetime.now(timezone.utc)
            campaign.total_recipients = len(contacts)
            campaign.delivered = int(result.get("sent", 0) or 0)
            db.add(campaign)
            db.commit()

        db.add(
            Log(
                message=(
                    f"Orchestration run-all: goal={goal}, drafts_created={drafts_created}"
                    + (f", remaining={remaining} queued as job {job_id}" if job_id else "")
                ),
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()

        return {
            "message": "Orchestration run-all completed",
            "goal": goal,
            "template_used": template.name,
            "drafts_created": drafts_created,
            "campaign_id": campaign.id if campaign is not None else None,
            "queued": bool(job_id),
            "job_id": job_id,
            "result": result
        }
    finally:
        db.close()


@router.post("/run-async", status_code=202)
async def run_orchestration_async(
    request: RunAllRequest = None,
    goal: str = None,
    template_id: int = None,
    tenant_id: int = Depends(current_tenant_id),
):
    """Queue a run-all pass on the background worker and return a job id.

    Same work as ``/run-all``, but the request returns immediately so a large
    batch never holds an HTTP connection open. Poll ``/jobs/{job_id}`` for the
    outcome; ``services/limits.py`` still gates every individual send.
    """
    from app.services.send_worker import drain_queue, get_worker

    if request is None:
        request = RunAllRequest()

    resolved_template_id = request.template_id or template_id
    contact_ids = list(request.contact_ids) if request.contact_ids else None
    list_id = request.list_id
    campaign_id = request.campaign_id

    # Validate before queuing so obvious mistakes are a 4xx, not a failed job.
    db = SessionLocal()
    try:
        campaign = None
        if campaign_id is not None:
            campaign = _load_campaign(db, tenant_id, campaign_id)
            resolved_template_id = resolved_template_id or campaign.template_id
            if campaign.list_id is not None:
                list_id = campaign.list_id
        _resolve_template(db, tenant_id, resolved_template_id)
    finally:
        db.close()

    async def runner():
        worker_db = SessionLocal()
        try:
            template = _resolve_template(worker_db, tenant_id, resolved_template_id)
            contacts = _select_contacts(worker_db, tenant_id, contact_ids, list_id)
            if not contacts:
                return {
                    "message": "No eligible contacts found",
                    "drafts_created": 0,
                    "result": {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []},
                }
            drafts_created = await _create_drafts(
                worker_db, tenant_id, template, contacts, campaign=campaign
            )
            worker_db.commit()
            if drafts_created == 0:
                return {
                    "message": "All eligible contacts already have pending drafts",
                    "drafts_created": 0,
                    "result": {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []},
                }
            # Already on the background worker, so drain the whole queue: the
            # pacing gaps are waited out here instead of by the caller.
            result = await drain_queue(tenant_id=tenant_id)

            if campaign is not None:
                campaign.status = "sent"
                campaign.sent_at = datetime.now(timezone.utc)
                campaign.total_recipients = len(contacts)
                campaign.delivered = int(result.get("sent", 0) or 0)
                worker_db.add(campaign)

            worker_db.add(
                Log(
                    message=(
                        "Orchestration run-async: "
                        f"drafts_created={drafts_created}"
                    ),
                    level="info",
                    tenant_id=tenant_id,
                )
            )
            worker_db.commit()
            return {
                "message": "Async run completed",
                "template_used": template.name,
                "drafts_created": drafts_created,
                "campaign_id": campaign.id if campaign is not None else None,
                "result": result,
            }
        finally:
            worker_db.close()

    job = get_worker().submit(tenant_id, runner)
    return job.to_dict()


@router.get("/jobs/{job_id}")
def get_send_job(job_id: str, tenant_id: int = Depends(current_tenant_id)):
    """Report the status and result of an async send job."""
    from app.services.send_worker import get_worker

    job = get_worker().get(job_id)
    # A job id from another tenant must not be readable, so it is a 404 here.
    if job is None or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.to_dict()


def _load_campaign(db, tenant_id: int, campaign_id: int):
    """The tenant's sendable campaign, or a 404/409/422 explaining why not."""
    from app.db import Campaign

    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        .first()
    )
    if not campaign:
        raise HTTPException(
            status_code=404, detail=f"Campaign {campaign_id} not found"
        )
    if campaign.status in {"sent", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail=f"Campaign is {campaign.status} and cannot be sent",
        )
    if campaign.channel and campaign.channel != "email":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Only email campaigns are supported; "
                f"'{campaign.channel}' needs a provider that is not configured."
            ),
        )
    return campaign


def _resolve_template(db, tenant_id: int, template_id: Optional[int]) -> Template:
    """The requested active template, or the tenant's first active one."""
    if template_id:
        template = (
            db.query(Template)
            .filter(
                Template.id == template_id,
                Template.tenant_id == tenant_id,
                Template.is_active == True,
            )
            .first()
        )
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template {template_id} not found or inactive",
            )
        return template

    template = (
        db.query(Template)
        .filter(Template.tenant_id == tenant_id, Template.is_active == True)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="No active template found")
    return template


def _select_contacts(
    db,
    tenant_id: int,
    contact_ids: Optional[List[int]],
    list_id: Optional[int],
) -> List[Contact]:
    """Eligible contacts for a run, always tenant-scoped.

    Addresses that can never receive mail are excluded up front so a run never
    drafts for a placeholder row; the queue enforces the same rule again at
    send time.
    """
    if list_id is not None:
        # Segment sends: the list must belong to this tenant, and the join is
        # what keeps a foreign contact id from slipping through.
        from app.db import ContactList, ContactListMember

        contact_list = (
            db.query(ContactList)
            .filter(
                ContactList.id == list_id,
                ContactList.tenant_id == tenant_id,
            )
            .first()
        )
        if not contact_list:
            raise HTTPException(status_code=404, detail=f"List {list_id} not found")

        contact_query = (
            db.query(Contact)
            .join(ContactListMember, ContactListMember.contact_id == Contact.id)
            .filter(
                Contact.tenant_id == tenant_id,
                ContactListMember.list_id == list_id,
                ContactListMember.tenant_id == tenant_id,
                Contact.eligible_to_email == True,
                Contact.email_blacklisted.isnot(True),
            )
        )
        if contact_ids:
            contact_query = contact_query.filter(Contact.id.in_(contact_ids))
        return [c for c in contact_query.all() if not blocked_reason(c.email)]

    if contact_ids:
        contacts = (
            db.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.id.in_(contact_ids),
                Contact.eligible_to_email == True,
                Contact.email_blacklisted.isnot(True),
            )
            .all()
        )
        found_ids = {contact.id for contact in contacts}
        missing = [cid for cid in contact_ids if cid not in found_ids]
        if missing:
            logger.warning(f"Some contact IDs not found or not eligible: {missing}")
        return [c for c in contacts if not blocked_reason(c.email)]

    return [
        contact
        for contact in (
            db.query(Contact)
            .filter(
                Contact.tenant_id == tenant_id,
                Contact.eligible_to_email == True,
                Contact.email_blacklisted.isnot(True),
            )
            .all()
        )
        if not blocked_reason(contact.email)
    ]


async def _create_drafts(
    db,
    tenant_id: int,
    template: Template,
    contacts,
    campaign=None,
) -> int:
    """Create one draft per contact that has none pending; return the count.

    When an experiment is running for ``template`` the draft uses the variant
    this contact is deterministically assigned to, and records the ids in
    ``variables`` so results survive variant edits.
    """
    from app.services.abtesting import (
        active_test_for_template,
        apply_variant,
        assignment_for_contact,
        variants_for_test,
    )

    drafts_created = 0
    ab_test = active_test_for_template(db, tenant_id, template.id)
    ab_variants = variants_for_test(db, ab_test) if ab_test is not None else []

    for contact in contacts:
        existing_draft = (
            db.query(Draft)
            .filter(
                Draft.tenant_id == tenant_id,
                Draft.contact_id == contact.id,
                Draft.status.in_(["draft", "blocked"]),
            )
            .first()
        )
        if existing_draft:
            continue

        try:
            expanded = await expand_template_with_ai(template, contact)
            subject = expanded["subject"]
            body = expanded["body"]
            variables = {"template_id": template.id}

            if ab_test is not None:
                assignment = assignment_for_contact(
                    ab_variants, ab_test.id, contact.id
                )
                if assignment is not None:
                    variant = assignment["variant"]
                    subject = variant.subject
                    body = variant.body
                    variables = apply_variant(variables, assignment)

            # A campaign's own subject wins over the template's, which is what
            # Brevo's campaign editor shows as the subject line.
            if campaign is not None:
                if campaign.subject:
                    subject = campaign.subject
                variables["campaign_id"] = campaign.id

            db.add(
                Draft(
                    contact_id=contact.id,
                    subject=subject,
                    body=body,
                    status="draft",
                    tenant_id=tenant_id,
                    campaign_id=campaign.id if campaign is not None else None,
                    variables=variables,
                )
            )
            record_usage(db, tenant_id, EMAILS_DRAFTED)
            drafts_created += 1
        except Exception as e:
            logger.warning(f"Failed to create draft for contact {contact.id}: {e}")
            continue

    return drafts_created
