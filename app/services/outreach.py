"""Automatic first-email outreach for eligible contacts.

Two entry points share one implementation:

* the CSV import route queues ``send_intro_to_imported_contacts`` for the rows
  it just added, and
* the agent pipeline calls ``create_intro_drafts`` with no ids, which covers
  every eligible contact that has never been emailed — so a contact added by
  hand is picked up by the next agent run without a separate button.

The caller always supplies its tenant, so this task can never draft for a
contact outside that tenant.
"""
import logging
from typing import List, Optional

from app.agents import EmailAgent, QueueManager
from app.db import Contact, Draft, Log, SessionLocal, Settings, Template
from app.services.provisioning import INTRO_CATEGORIES

logger = logging.getLogger(__name__)


def _open_draft_exists(db, tenant_id: Optional[int], contact_id: int) -> bool:
    query = db.query(Draft).filter(
        Draft.contact_id == contact_id,
        Draft.status.in_(["sent", "draft", "sending", "blocked"]),
    )
    if tenant_id is not None:
        query = query.filter(Draft.tenant_id == tenant_id)
    # Follow-ups belong to an existing thread, so they are not "prior outreach".
    return any(
        not (draft.variables or {}).get("followup_for") for draft in query.all()
    )


async def create_intro_drafts(
    contact_ids: Optional[List[int]] = None,
    tenant_id: Optional[int] = None,
    require_automation: bool = False,
) -> dict:
    """Create one intro draft per eligible contact that has none.

    ``contact_ids=None`` means "every eligible contact without prior outreach",
    which is what a manual agent run uses. ``require_automation`` keeps the
    import path opt-in (it only drafts when autopilot and auto-approve are on);
    a run the user triggered explicitly passes ``False``.
    """
    db = SessionLocal()
    created = 0
    try:
        if require_automation:
            settings_query = db.query(Settings)
            if tenant_id is not None:
                settings_query = settings_query.filter(
                    Settings.tenant_id == tenant_id
                )
            settings = settings_query.first()
            if not settings or not settings.AUTOPILOT or not settings.AUTO_APPROVE:
                return {"created": 0, "skipped": 0, "reason": "automation disabled"}

        # Older deployments (init_templates.py) stored the intro template under
        # "personalized_mail"; accept every known alias so an existing template
        # is not silently ignored.
        template_query = db.query(Template).filter(
            Template.is_active == True,
            Template.category.in_(INTRO_CATEGORIES),
        )
        if tenant_id is not None:
            template_query = template_query.filter(Template.tenant_id == tenant_id)
        template = template_query.first()
        if not template:
            db.add(
                Log(
                    message=(
                        "Automatic outreach skipped: no active intro template "
                        "is configured"
                    ),
                    level="warning",
                    tenant_id=tenant_id,
                )
            )
            db.commit()
            return {"created": 0, "skipped": 0, "reason": "no intro template"}

        contact_query = db.query(Contact).filter(Contact.eligible_to_email == True)
        if tenant_id is not None:
            contact_query = contact_query.filter(Contact.tenant_id == tenant_id)
        if contact_ids is not None:
            contact_query = contact_query.filter(Contact.id.in_(contact_ids))
        contacts = contact_query.all()

        skipped = 0
        for contact in contacts:
            if _open_draft_exists(db, tenant_id, contact.id):
                skipped += 1
                continue

            result = await EmailAgent(contact.id, template.id).run(
                auto_approve=False,
                send_via_smtp=False,
            )
            if not result.get("success"):
                logger.warning(
                    "Could not create intro draft for contact %s: %s",
                    contact.id,
                    result.get("error", "unknown error"),
                )
                continue

            # EmailAgent commits its draft in its own session, so end this
            # transaction first: under REPEATABLE READ the open snapshot would
            # never see the row and the draft would go uncounted.
            db.commit()
            draft_query = db.query(Draft).filter(Draft.id == result["draft_id"])
            if tenant_id is not None:
                draft_query = draft_query.filter(Draft.tenant_id == tenant_id)
            draft = draft_query.first()
            if draft:
                draft.variables = {"campaign_type": "intro"}
                created += 1

        if created:
            db.add(
                Log(
                    message=f"Created {created} automatic intro draft(s)",
                    level="info",
                    tenant_id=tenant_id,
                )
            )
        db.commit()
        return {"created": created, "skipped": skipped, "reason": None}
    except Exception:
        db.rollback()
        logger.exception("Automatic intro outreach failed")
        raise
    finally:
        db.close()


async def send_intro_to_imported_contacts(
    contact_ids: List[int],
    tenant_id: Optional[int] = None,
) -> None:
    """Import hook: draft, then send, for the rows that were just imported."""
    result = await create_intro_drafts(
        contact_ids=contact_ids, tenant_id=tenant_id, require_automation=True
    )
    if not result.get("created"):
        return

    db = SessionLocal()
    try:
        queue_result = await QueueManager().process_queue(tenant_id=tenant_id)
        db.add(
            Log(
                message=(
                    f"Automatic intro outreach processed: "
                    f"{queue_result.get('sent', 0)} sent, "
                    f"{queue_result.get('failed', 0)} failed, "
                    f"{queue_result.get('skipped', 0)} skipped"
                ),
                level="info" if not queue_result.get("error") else "warning",
                tenant_id=tenant_id,
            )
        )
        db.commit()
    finally:
        db.close()
