"""Create due follow-up drafts (day 3 and day 5, stopping after day 8).

Drafts are never sent automatically; they still need approval in the UI.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db import Contact, Draft, Log, SessionLocal, Template

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


async def generate_followups(now: Optional[datetime] = None) -> dict:
    """Return ``{"created": n, "skipped": n}`` for due follow-ups."""
    from app.agents import expand_template_with_ai

    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    created = 0
    skipped = 0
    try:
        sent_drafts = (
            db.query(Draft)
            .filter(Draft.status == "sent", Draft.sent_at.isnot(None))
            .all()
        )
        template = (
            db.query(Template)
            .filter(Template.is_active == True, Template.category == "followup")
            .first()
        )

        for original in sent_drafts:
            sent_at = _as_utc(original.sent_at)
            if sent_at is None:
                continue
            stage = _stage_for_age((now - sent_at).days)
            if stage is None:
                continue

            existing = db.query(Draft).filter(Draft.contact_id == original.contact_id).all()
            already_queued = any(
                (draft.variables or {}).get("followup_for") == original.id
                and (draft.variables or {}).get("followup_stage") == stage
                for draft in existing
            )
            if already_queued:
                skipped += 1
                continue

            contact = db.query(Contact).filter(Contact.id == original.contact_id).first()
            if not contact:
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
                )
            )
            created += 1

        if created:
            db.add(Log(message=f"Created {created} follow-up draft(s)", level="info"))
        db.commit()
        return {"created": created, "skipped": skipped}
    except Exception as exc:
        db.rollback()
        logger.error("Follow-up generation failed: %s", exc)
        raise
    finally:
        db.close()
