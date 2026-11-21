"""Create due follow-up drafts (day 3 and day 5, stopping after day 8).

Pass ``tenant_id`` to restrict the pass to one tenant. Omitting it processes
every tenant in a single sweep, which is only appropriate for a maintenance
job — HTTP callers always pass their own tenant.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db import Contact, Draft, Event, Log, SessionLocal, Template, Tenant
from app.services.provisioning import FOLLOWUP_CATEGORIES

logger = logging.getLogger(__name__)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _stage_for_age(days: int) -> Optional[int]:
    if 3 <= days < 5:
        return 3
    if 5 <= days < 8:
        return 5
    return None


async def generate_followups(
    now: Optional[datetime] = None,
    tenant_id: Optional[int] = None,
) -> dict:
    """Return ``{"created": n, "skipped": n}`` for due follow-ups.

    With no ``tenant_id`` the pass sweeps every tenant separately (each tenant's
    drafts stay isolated). When no tenant rows exist at all — a single-user
    install — it falls back to one unscoped pass over legacy rows.
    """
    if tenant_id is None:
        db = SessionLocal()
        try:
            tenant_ids = [row[0] for row in db.query(Tenant.id).all()]
        finally:
            db.close()
        if tenant_ids:
            totals = {"created": 0, "skipped": 0}
            for single_tenant in tenant_ids:
                result = await generate_followups(now=now, tenant_id=single_tenant)
                totals["created"] += result["created"]
                totals["skipped"] += result["skipped"]
            return totals

    return await _generate_followups_for_tenant(now=now, tenant_id=tenant_id)


async def _generate_followups_for_tenant(
    now: Optional[datetime] = None,
    tenant_id: Optional[int] = None,
) -> dict:
    from app.agents import expand_template_with_ai

    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    created = 0
    skipped = 0
    try:
        sent_query = db.query(Draft).filter(
            Draft.status == "sent", Draft.sent_at.isnot(None)
        )
        # "followups_mail" is the legacy spelling written by init_templates.py;
        # both are accepted and provisioning migrates the old one on startup.
        template_query = db.query(Template).filter(
            Template.is_active == True,
            Template.category.in_(FOLLOWUP_CATEGORIES),
        )
        if tenant_id is not None:
            sent_query = sent_query.filter(Draft.tenant_id == tenant_id)
            template_query = template_query.filter(Template.tenant_id == tenant_id)
        sent_drafts = sent_query.all()
        template = template_query.first()

        for original in sent_drafts:
            variables = original.variables or {}
            if variables.get("followup_for") or variables.get("message_kind") == "auto_reply":
                continue
            sent_at = _as_utc(original.sent_at)
            if sent_at is None:
                continue
            stage = _stage_for_age((now - sent_at).days)
            if stage is None:
                continue

            replied = (
                db.query(Event.id)
                .filter(
                    Event.tenant_id == tenant_id,
                    Event.contact_id == original.contact_id,
                    Event.event_type == "reply_received",
                    Event.timestamp >= sent_at,
                )
                .first()
            )
            if replied:
                skipped += 1
                continue

            existing = (
                db.query(Draft)
                .filter(
                    Draft.tenant_id == tenant_id,
                    Draft.contact_id == original.contact_id,
                )
                .all()
            )
            original_followups = [
                draft
                for draft in existing
                if (draft.variables or {}).get("followup_for") == original.id
            ]
            if stage == 5 and any(
                (draft.variables or {}).get("followup_stage") == 3
                and draft.status != "sent"
                for draft in original_followups
            ):
                skipped += 1
                continue
            already_queued = any(
                (draft.variables or {}).get("followup_for") == original.id
                and (draft.variables or {}).get("followup_stage") == stage
                for draft in existing
            )
            if already_queued:
                skipped += 1
                continue

            contact = (
                db.query(Contact)
                .filter(
                    Contact.id == original.contact_id,
                    Contact.tenant_id == tenant_id,
                )
                .first()
            )
            if not contact or not contact.eligible_to_email:
                skipped += 1
                continue

            if template:
                expanded = await expand_template_with_ai(template, contact)
                subject = expanded["subject"]
                body = expanded["body"]
            else:
                first_name = (contact.name or "there").split()[0]
                subject = f"Re: {original.subject}"
                body = (
                    f"Hi {first_name},\n\n"
                    "Just following up on my previous note - happy to share more "
                    "if it is useful.\n\nBest regards"
                )

            db.add(
                Draft(
                    contact_id=contact.id,
                    subject=subject,
                    body=body,
                    status="draft",
                    variables={"followup_for": original.id, "followup_stage": stage},
                    tenant_id=tenant_id,
                )
            )
            created += 1

        if created:
            db.add(
                Log(
                    message=f"Created {created} follow-up draft(s)",
                    level="info",
                    tenant_id=tenant_id,
                )
            )
        db.commit()
        return {"created": created, "skipped": skipped}
    except Exception as exc:
        db.rollback()
        logger.error("Follow-up generation failed: %s", exc)
        raise
    finally:
        db.close()
