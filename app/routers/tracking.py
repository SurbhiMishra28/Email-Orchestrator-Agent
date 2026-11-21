"""Read-only mail, reply, and follow-up tracking (tenant-scoped)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.db import Contact, Draft, Event, SessionLocal
from app.deps import current_tenant_id

router = APIRouter()


@router.get("")
def get_tracking(tenant_id: int = Depends(current_tenant_id)):
    """Return the tenant's contact status and persisted reply/follow-up history."""
    db = SessionLocal()
    try:
        contacts = (
            db.query(Contact)
            .filter(Contact.tenant_id == tenant_id)
            .order_by(Contact.email.asc())
            .all()
        )
        drafts = (
            db.query(Draft)
            .filter(Draft.tenant_id == tenant_id)
            .order_by(Draft.created_at.desc())
            .limit(5000)
            .all()
        )
        events = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant_id,
                Event.event_type.in_(
                    [
                        "reply_received",
                        "auto_reply_queued",
                        "auto_reply_sent",
                        "auto_reply_failed",
                        "email_opened",
                        "link_clicked",
                    ]
                ),
            )
            .order_by(Event.timestamp.desc())
            .limit(5000)
            .all()
        )

        drafts_by_contact = {}
        drafts_by_id = {}
        for draft in drafts:
            drafts_by_contact.setdefault(draft.contact_id, []).append(draft)
            drafts_by_id[draft.id] = draft

        replies_by_contact = {}
        auto_replies_by_contact = {}
        auto_reply_by_event = {}
        opened_drafts = set()
        clicked_drafts = set()
        for event in events:
            if event.event_type == "reply_received":
                replies_by_contact.setdefault(event.contact_id, []).append(event)
            elif event.event_type in {"email_opened", "link_clicked"}:
                draft_id = (event.data or {}).get("draft_id")
                if draft_id is not None:
                    if event.event_type == "email_opened":
                        opened_drafts.add(draft_id)
                    else:
                        clicked_drafts.add(draft_id)
            else:
                auto_replies_by_contact[event.contact_id] = (
                    auto_replies_by_contact.get(event.contact_id, 0)
                    + int(event.event_type == "auto_reply_sent")
                )
                auto_reply_by_event.setdefault(
                    (event.data or {}).get("reply_event_id"), event
                )

        followups = []
        emails = []
        for contact in contacts:
            contact_drafts = drafts_by_contact.get(contact.id, [])
            contact_replies = replies_by_contact.get(contact.id, [])
            outbound = [
                draft
                for draft in contact_drafts
                if not (draft.variables or {}).get("followup_for")
                and (draft.variables or {}).get("message_kind") != "auto_reply"
            ]
            latest_outbound = outbound[0] if outbound else None
            sent_outbound = [draft for draft in outbound if draft.status == "sent"]
            original = sent_outbound[0] if sent_outbound else None
            latest_reply = contact_replies[0] if contact_replies else None
            classification = (
                (latest_reply.data or {}).get("classification", {})
                if latest_reply
                else {}
            )
            reply_type = classification.get("reply_type")
            if reply_type == "positive_response":
                interest = "Interested"
            elif reply_type in {"negative_response", "spam"}:
                interest = "Not interested"
            elif reply_type:
                interest = "Replied"
            elif original:
                interest = "Awaiting reply"
            else:
                interest = "Not contacted"

            contact_followups = [
                draft
                for draft in contact_drafts
                if (draft.variables or {}).get("followup_for")
            ]
            sent_followups = [
                draft for draft in contact_followups if draft.status == "sent"
            ]
            queued_stages = {
                (draft.variables or {}).get("followup_stage")
                for draft in contact_followups
                if draft.status in {"draft", "blocked", "sending"}
                and (draft.variables or {}).get("followup_stage") is not None
            }

            next_action = "Not sent"
            if latest_reply and (
                not original
                or not original.sent_at
                or latest_reply.timestamp >= original.sent_at
            ):
                next_action = "Stopped after reply"
            elif original and original.sent_at:
                age_days = (
                    datetime.now(timezone.utc) - original.sent_at
                ).days
                sent_stages = {
                    (draft.variables or {}).get("followup_stage")
                    for draft in sent_followups
                }
                if age_days >= 8 and queued_stages:
                    next_action = (
                        f"Follow-up queued (day {min(queued_stages)})"
                    )
                elif 3 <= age_days < 5 and 3 not in sent_stages:
                    next_action = (
                        "Follow-up queued (day 3)"
                        if 3 in queued_stages
                        else "Follow-up due (day 3)"
                    )
                elif 5 <= age_days < 8 and 5 not in sent_stages:
                    if 5 in queued_stages:
                        next_action = "Follow-up queued (day 5)"
                    elif 3 in queued_stages:
                        next_action = "Follow-up queued (day 3)"
                    else:
                        next_action = "Follow-up due (day 5)"
                elif age_days >= 8:
                    next_action = "Follow-up sequence complete"
                elif sent_stages:
                    next_action = "Follow-up sent"
                else:
                    next_action = "Waiting"

            emails.append(
                {
                    "contact_id": contact.id,
                    "email": contact.email,
                    "name": contact.name,
                    "eligible_to_email": contact.eligible_to_email,
                    "last_email_status": (
                        latest_outbound.status if latest_outbound else None
                    ),
                    "last_email_sent_at": (
                        latest_outbound.sent_at.isoformat()
                        if latest_outbound and latest_outbound.sent_at
                        else None
                    ),
                    "interest": interest,
                    "reply_count": len(contact_replies),
                    "auto_replies_sent": auto_replies_by_contact.get(contact.id, 0),
                    "followups_sent": len(sent_followups),
                    "next_action": next_action,
                    "opened": any(d.id in opened_drafts for d in sent_outbound),
                    "clicked": any(d.id in clicked_drafts for d in sent_outbound),
                }
            )

            for draft in contact_followups:
                original_followup = drafts_by_id.get(
                    (draft.variables or {}).get("followup_for")
                )
                followups.append(
                    {
                        "id": draft.id,
                        "contact_id": contact.id,
                        "email": contact.email,
                        "subject": draft.subject,
                        "stage": (draft.variables or {}).get("followup_stage"),
                        "status": draft.status,
                        "created_at": (
                            draft.created_at.isoformat() if draft.created_at else None
                        ),
                        "sent_at": draft.sent_at.isoformat() if draft.sent_at else None,
                        "error_message": draft.error_message,
                        "original_subject": (
                            original_followup.subject if original_followup else None
                        ),
                    }
                )

        replies = []
        for event in events:
            if event.event_type != "reply_received":
                continue
            data = event.data or {}
            classification = data.get("classification", {})
            auto_reply = auto_reply_by_event.get(event.id)
            replies.append(
                {
                    "id": event.id,
                    "contact_id": event.contact_id,
                    "email": data.get("sender_email", ""),
                    "subject": data.get("subject", ""),
                    "body_preview": data.get("body_preview", ""),
                    "reply_type": classification.get("reply_type", "unknown"),
                    "sentiment": classification.get("sentiment", "unknown"),
                    "received_at": event.timestamp.isoformat() if event.timestamp else None,
                    "auto_reply_status": (
                        "sent"
                        if auto_reply and auto_reply.event_type == "auto_reply_sent"
                        else "failed"
                        if auto_reply and auto_reply.event_type == "auto_reply_failed"
                        else "queued"
                        if auto_reply and auto_reply.event_type == "auto_reply_queued"
                        else "not sent"
                    ),
                    "auto_reply_message": (
                        (auto_reply.data or {}).get("message") if auto_reply else None
                    ),
                }
            )

        return {
            "emails": emails,
            "followups": followups,
            "replies": replies,
            "reply_count": len(replies),
            "auto_replies_sent": sum(auto_replies_by_contact.values()),
            "opened_drafts": len(opened_drafts),
            "clicked_drafts": len(clicked_drafts),
        }
    finally:
        db.close()
