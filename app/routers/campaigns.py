"""Campaigns API, modelled on Brevo's Campaigns product.

Brevo's campaigns page is a listing of outbound sends. Each campaign targets a
contact list (or every eligible contact), uses a template, and moves through
draft -> scheduled -> sending -> sent, with a pause/cancel escape hatch. The
listing shows the counters Brevo shows: recipients, delivered, opened, clicked,
replied, bounced and unsubscribed.

Everything here is tenant-scoped, and a foreign id is reported as 404 so one
tenant's campaign can never be read, edited or sent by another.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.db import (
    Campaign,
    Contact,
    ContactList,
    ContactListMember,
    Draft,
    Event,
    SessionLocal,
    Template,
)
from app.deps import current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {
    "draft",
    "scheduled",
    "sending",
    "sent",
    "paused",
    "cancelled",
}
# Email only. SMS, push and WhatsApp need providers this app does not ship, so
# they are rejected rather than stored as campaigns that can never send.
VALID_CHANNELS = {"email"}

# Kept for the listing's supported_channels field.
SUPPORTED_CHANNELS = {"email"}


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    subject: Optional[str] = Field(default=None, max_length=500)
    preview_text: Optional[str] = Field(default=None, max_length=500)
    channel: str = "email"
    template_id: Optional[int] = None
    templateId: Optional[int] = None
    list_id: Optional[int] = None
    listId: Optional[int] = None
    # Brevo targets several lists per campaign and can subtract an exclusion
    # list, so both the snake_case and Brevo camelCase spellings are accepted.
    list_ids: Optional[List[int]] = None
    listIds: Optional[List[int]] = None
    exclude_list_ids: Optional[List[int]] = None
    excludeListIds: Optional[List[int]] = None
    campaign_type: str = "marketing"
    campaignType: Optional[str] = None
    timezone: Optional[str] = None
    ab_test_id: Optional[int] = None
    abTestId: Optional[int] = None
    scheduled_at: Optional[str] = None
    scheduledAt: Optional[str] = None
    # Sender identity. ``alias_id`` is resolved to the alias's name/address; the
    # explicit fields are accepted too so an API client can pin a From address
    # that is not in the alias table.
    alias_id: Optional[int] = None
    aliasId: Optional[int] = None
    from_email: Optional[str] = Field(default=None, max_length=255)
    fromEmail: Optional[str] = Field(default=None, max_length=255)
    from_name: Optional[str] = Field(default=None, max_length=255)
    fromName: Optional[str] = Field(default=None, max_length=255)


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    subject: Optional[str] = Field(default=None, max_length=500)
    preview_text: Optional[str] = Field(default=None, max_length=500)
    channel: Optional[str] = None
    template_id: Optional[int] = None
    templateId: Optional[int] = None
    list_id: Optional[int] = None
    listId: Optional[int] = None
    list_ids: Optional[List[int]] = None
    listIds: Optional[List[int]] = None
    exclude_list_ids: Optional[List[int]] = None
    excludeListIds: Optional[List[int]] = None
    campaign_type: Optional[str] = None
    campaignType: Optional[str] = None
    timezone: Optional[str] = None
    ab_test_id: Optional[int] = None
    abTestId: Optional[int] = None
    status: Optional[str] = None
    scheduled_at: Optional[str] = None
    scheduledAt: Optional[str] = None
    alias_id: Optional[int] = None
    aliasId: Optional[int] = None
    from_email: Optional[str] = Field(default=None, max_length=255)
    fromEmail: Optional[str] = Field(default=None, max_length=255)
    from_name: Optional[str] = Field(default=None, max_length=255)
    fromName: Optional[str] = Field(default=None, max_length=255)


class CampaignOut(BaseModel):
    id: int
    name: str
    subject: Optional[str] = None
    preview_text: Optional[str] = None
    channel: str = "email"
    status: str = "draft"
    template_id: Optional[int] = None
    templateId: Optional[int] = None
    list_id: Optional[int] = None
    listId: Optional[int] = None
    list_ids: List[int] = []
    listIds: List[int] = []
    exclude_list_ids: List[int] = []
    excludeListIds: List[int] = []
    list_names: List[str] = []
    campaign_type: str = "marketing"
    timezone: Optional[str] = None
    ab_test_id: Optional[int] = None
    abTestId: Optional[int] = None
    list_name: Optional[str] = None
    template_name: Optional[str] = None
    # The sender identity this campaign uses, echoed so the listing can show it.
    from_email: Optional[str] = None
    fromEmail: Optional[str] = None
    from_name: Optional[str] = None
    fromName: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    total_recipients: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
    bounced: int = 0
    unsubscribed: int = 0
    spam_complaints: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- helpers


def _get_campaign(db, campaign_id: int, tenant_id: int) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _resolve_template(db, tenant_id: int, payload) -> Optional[int]:
    template_id = (
        getattr(payload, "template_id", None)
        if getattr(payload, "template_id", None) is not None
        else getattr(payload, "templateId", None)
    )
    if template_id is None:
        return None
    exists = (
        db.query(Template.id)
        .filter(Template.id == template_id, Template.tenant_id == tenant_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return template_id


def _resolve_list(db, tenant_id: int, payload) -> Optional[int]:
    list_id = (
        getattr(payload, "list_id", None)
        if getattr(payload, "list_id", None) is not None
        else getattr(payload, "listId", None)
    )
    if list_id is None:
        return None
    exists = (
        db.query(ContactList.id)
        .filter(ContactList.id == list_id, ContactList.tenant_id == tenant_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"List {list_id} not found")
    return list_id


def _resolve_sender(db, tenant_id: int, payload) -> tuple:
    """Resolve the campaign's sender to ``(from_email, from_name)``.

    Precedence: an explicit ``from_email`` on the payload, then the named alias.
    When neither is given the tenant's default alias is used, and if the tenant
    has no aliases at all both come back empty so the mailer falls back to the
    mailbox's own address rather than failing the send.
    """
    from app.db import EmailAlias

    explicit_email = (
        getattr(payload, "from_email", None) or getattr(payload, "fromEmail", None)
    )
    explicit_name = (
        getattr(payload, "from_name", None) or getattr(payload, "fromName", None)
    )

    alias_id = (
        getattr(payload, "alias_id", None)
        if getattr(payload, "alias_id", None) is not None
        else getattr(payload, "aliasId", None)
    )

    query = db.query(EmailAlias).filter(
        EmailAlias.tenant_id == tenant_id,
        EmailAlias.is_active.is_(True),
    )
    if alias_id is not None:
        alias = query.filter(EmailAlias.id == alias_id).first()
        if alias is None:
            raise HTTPException(
                status_code=404, detail=f"Alias {alias_id} not found"
            )
    else:
        alias = query.filter(EmailAlias.is_default.is_(True)).first()

    if explicit_email:
        return str(explicit_email).strip(), (explicit_name or "").strip() or None
    if alias is not None:
        return alias.email, (explicit_name or alias.name or "").strip() or None
    return None, (explicit_name or "").strip() or None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="scheduled_at must be an ISO date-time"
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scheduled_value(payload) -> Optional[datetime]:
    raw = getattr(payload, "scheduled_at", None) or getattr(payload, "scheduledAt", None)
    return _parse_datetime(raw)


def _selected_list_ids(payload, fallback: Optional[int] = None) -> List[int]:
    """Every list id a payload targets, de-duplicated and order-stable.

    Brevo's UI sends ``listIds``; the single-list field stays supported so older
    clients (and the scheduler) keep working.
    """
    raw = getattr(payload, "list_ids", None) or getattr(payload, "listIds", None) or []
    ids: List[int] = []
    for value in raw:
        try:
            list_id = int(value)
        except (TypeError, ValueError):
            continue
        if list_id not in ids:
            ids.append(list_id)
    single = (
        getattr(payload, "list_id", None)
        if getattr(payload, "list_id", None) is not None
        else getattr(payload, "listId", None)
    )
    if single is not None and int(single) not in ids:
        ids.insert(0, int(single))
    if not ids and fallback is not None:
        ids.append(int(fallback))
    return ids


def _excluded_list_ids(payload) -> List[int]:
    raw = (
        getattr(payload, "exclude_list_ids", None)
        or getattr(payload, "excludeListIds", None)
        or []
    )
    ids: List[int] = []
    for value in raw:
        try:
            list_id = int(value)
        except (TypeError, ValueError):
            continue
        if list_id not in ids:
            ids.append(list_id)
    return ids


def _validate_list_ids(db, tenant_id: int, list_ids: List[int]) -> None:
    """A list id must belong to the tenant, else the send could reach strangers."""
    if not list_ids:
        return
    owned = {
        row[0]
        for row in db.query(ContactList.id).filter(
            ContactList.id.in_(list_ids), ContactList.tenant_id == tenant_id
        )
    }
    missing = [list_id for list_id in list_ids if list_id not in owned]
    if missing:
        raise HTTPException(status_code=404, detail=f"List(s) not found: {missing}")


def _audience_query(db, tenant_id: int, list_ids: List[int], exclude_ids: List[int]):
    """Contacts a campaign would mail, as a query.

    With no lists the audience is every eligible contact in the tenant. With
    lists it is the union of their subscribed members, minus anyone on an
    exclusion list and minus unsubscribed/blacklisted contacts.
    """
    eligible = [
        Contact.tenant_id == tenant_id,
        Contact.eligible_to_email.is_(True),
        Contact.email_blacklisted.isnot(True),
    ]
    if not list_ids:
        return db.query(Contact).filter(*eligible)

    member_lists = (
        db.query(ContactListMember.contact_id)
        .filter(
            ContactListMember.tenant_id == tenant_id,
            ContactListMember.list_id.in_(list_ids),
            ContactListMember.unsubscribed.isnot(True),
        )
        .subquery()
    )
    # A contact in two selected lists has two membership rows; filtering with
    # ``IN`` keeps one row per contact so counts and sends do not double up.
    query = (
        db.query(Contact)
        .filter(*eligible, Contact.id.in_(db.query(member_lists.c.contact_id)))
    )
    if exclude_ids:
        excluded = (
            db.query(ContactListMember.contact_id)
            .filter(
                ContactListMember.tenant_id == tenant_id,
                ContactListMember.list_id.in_(exclude_ids),
            )
            .subquery()
        )
        query = query.filter(~Contact.id.in_(db.query(excluded.c.contact_id)))
    return query


def _audience_size(
    db, tenant_id: int, list_id: Optional[int], exclude_ids: Optional[List[int]] = None
) -> int:
    """Count the contacts a campaign would send to."""
    list_ids = [list_id] if list_id is not None else []
    return _audience_query(db, tenant_id, list_ids, exclude_ids or []).count()


def _to_out(db, campaign: Campaign, tenant_id: int) -> CampaignOut:
    list_ids = list(campaign.list_ids or [])
    if not list_ids and campaign.list_id is not None:
        list_ids = [campaign.list_id]
    exclude_ids = list(campaign.exclude_list_ids or [])

    list_name = None
    if campaign.list_id is not None:
        list_name = (
            db.query(ContactList.name)
            .filter(
                ContactList.id == campaign.list_id,
                ContactList.tenant_id == tenant_id,
            )
            .scalar()
        )
    list_names: List[str] = []
    if list_ids:
        rows = (
            db.query(ContactList.id, ContactList.name)
            .filter(ContactList.id.in_(list_ids), ContactList.tenant_id == tenant_id)
            .all()
        )
        by_id = {row[0]: row[1] for row in rows}
        list_names = [by_id[list_id] for list_id in list_ids if list_id in by_id]
    template_name = None
    if campaign.template_id is not None:
        template_name = (
            db.query(Template.name)
            .filter(
                Template.id == campaign.template_id,
                Template.tenant_id == tenant_id,
            )
            .scalar()
        )

    base = campaign.delivered or campaign.total_recipients or 0
    open_rate = round(campaign.opened / base * 100, 1) if base else 0.0
    click_rate = round(campaign.clicked / base * 100, 1) if base else 0.0

    return CampaignOut(
        id=campaign.id,
        name=campaign.name,
        subject=campaign.subject,
        preview_text=campaign.preview_text,
        channel=campaign.channel or "email",
        status=campaign.status or "draft",
        template_id=campaign.template_id,
        templateId=campaign.template_id,
        list_id=campaign.list_id,
        listId=campaign.list_id,
        list_ids=list_ids,
        listIds=list_ids,
        exclude_list_ids=exclude_ids,
        excludeListIds=exclude_ids,
        list_names=list_names,
        campaign_type=campaign.campaign_type or "marketing",
        timezone=campaign.timezone,
        ab_test_id=campaign.ab_test_id,
        abTestId=campaign.ab_test_id,
        list_name=list_name,
        template_name=template_name,
        from_email=campaign.from_email,
        fromEmail=campaign.from_email,
        from_name=campaign.from_name,
        fromName=campaign.from_name,
        scheduled_at=campaign.scheduled_at,
        sent_at=campaign.sent_at,
        total_recipients=campaign.total_recipients or 0,
        delivered=campaign.delivered or 0,
        opened=campaign.opened or 0,
        clicked=campaign.clicked or 0,
        replied=campaign.replied or 0,
        bounced=campaign.bounced or 0,
        unsubscribed=campaign.unsubscribed or 0,
        open_rate=open_rate,
        click_rate=click_rate,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )
    return status


def _validate_channel(channel: str) -> str:
    if channel not in VALID_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"channel must be one of {sorted(VALID_CHANNELS)}",
        )
    return channel


VALID_CAMPAIGN_TYPES = {"marketing", "transactional"}


def _validate_campaign_type(value: str) -> str:
    """Marketing needs consent; transactional is triggered by the recipient."""
    if value not in VALID_CAMPAIGN_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"campaign_type must be one of {sorted(VALID_CAMPAIGN_TYPES)}",
        )
    return value


def _resolve_ab_test(db, tenant_id: int, payload) -> Optional[int]:
    """Validate an attached experiment belongs to the tenant."""
    from app.db import ABTest

    raw = (
        getattr(payload, "ab_test_id", None)
        if getattr(payload, "ab_test_id", None) is not None
        else getattr(payload, "abTestId", None)
    )
    if raw is None:
        return None
    test_id = int(raw)
    exists = (
        db.query(ABTest.id)
        .filter(ABTest.id == test_id, ABTest.tenant_id == tenant_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"A/B test {test_id} not found")
    return test_id


# ------------------------------------------------------------------ routes


@router.get("", response_model=List[CampaignOut])
def list_campaigns(
    status: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(300, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("desc", pattern="^(asc|desc)$"),
    tenant_id: int = Depends(current_tenant_id),
):
    """List campaigns newest first, filtered the way Brevo's listing filters."""
    db = SessionLocal()
    try:
        query = db.query(Campaign).filter(Campaign.tenant_id == tenant_id)
        if status:
            query = query.filter(Campaign.status == _validate_status(status))
        if channel:
            query = query.filter(Campaign.channel == _validate_channel(channel))
        if search:
            query = query.filter(Campaign.name.ilike(f"%{search.strip()}%"))

        if sort == "desc":
            query = query.order_by(Campaign.created_at.desc(), Campaign.id.desc())
        else:
            query = query.order_by(Campaign.created_at.asc(), Campaign.id.asc())

        rows = query.offset(offset).limit(limit).all()
        return [_to_out(db, row, tenant_id) for row in rows]
    finally:
        db.close()


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(
    payload: CampaignCreate, tenant_id: int = Depends(current_tenant_id)
):
    """Create a draft campaign, optionally scheduled and targeted at a list."""
    channel = _validate_channel(payload.channel or "email")
    scheduled_at = _scheduled_value(payload)
    campaign_type = _validate_campaign_type(
        payload.campaign_type or payload.campaignType or "marketing"
    )

    db = SessionLocal()
    try:
        template_id = _resolve_template(db, tenant_id, payload)
        list_ids = _selected_list_ids(payload)
        _validate_list_ids(db, tenant_id, list_ids)
        excluded_ids = _excluded_list_ids(payload)
        _validate_list_ids(db, tenant_id, excluded_ids)
        from_email, from_name = _resolve_sender(db, tenant_id, payload)
        ab_test_id = _resolve_ab_test(db, tenant_id, payload)

        campaign = Campaign(
            tenant_id=tenant_id,
            name=payload.name,
            subject=payload.subject,
            preview_text=payload.preview_text,
            channel=channel,
            status="scheduled" if scheduled_at else "draft",
            template_id=template_id,
            list_id=list_ids[0] if list_ids else None,
            list_ids=list_ids,
            exclude_list_ids=excluded_ids,
            campaign_type=campaign_type,
            timezone=payload.timezone,
            ab_test_id=ab_test_id,
            scheduled_at=scheduled_at,
            total_recipients=_audience_query(
                db, tenant_id, list_ids, excluded_ids
            ).count(),
            from_email=from_email,
            from_name=from_name,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return _to_out(db, campaign, tenant_id)
    finally:
        db.close()


@router.get("/summary")
def campaigns_summary(tenant_id: int = Depends(current_tenant_id)):
    """Counts per status and channel for the listing header."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Campaign.status, func.count(Campaign.id))
            .filter(Campaign.tenant_id == tenant_id)
            .group_by(Campaign.status)
            .all()
        )
        by_status: Dict[str, int] = {status: count for status, count in rows}
        channel_rows = (
            db.query(Campaign.channel, func.count(Campaign.id))
            .filter(Campaign.tenant_id == tenant_id)
            .group_by(Campaign.channel)
            .all()
        )
        by_channel: Dict[str, int] = {
            channel or "email": count for channel, count in channel_rows
        }
        sent_totals = (
            db.query(
                func.coalesce(func.sum(Campaign.delivered), 0),
                func.coalesce(func.sum(Campaign.opened), 0),
                func.coalesce(func.sum(Campaign.clicked), 0),
                func.coalesce(func.sum(Campaign.replied), 0),
            )
            .filter(Campaign.tenant_id == tenant_id, Campaign.status == "sent")
            .first()
        )
        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "by_channel": by_channel,
            "sent_totals": {
                "delivered": int(sent_totals[0] or 0) if sent_totals else 0,
                "opened": int(sent_totals[1] or 0) if sent_totals else 0,
                "clicked": int(sent_totals[2] or 0) if sent_totals else 0,
                "replied": int(sent_totals[3] or 0) if sent_totals else 0,
            },
            "supported_channels": sorted(SUPPORTED_CHANNELS),
        }
    finally:
        db.close()


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        return _to_out(db, _get_campaign(db, campaign_id, tenant_id), tenant_id)
    finally:
        db.close()


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    """Update a campaign. A sent campaign can only be renamed, never re-sent."""
    db = SessionLocal()
    try:
        campaign = _get_campaign(db, campaign_id, tenant_id)

        if campaign.status == "sent" and payload.status not in (None, "sent"):
            raise HTTPException(
                status_code=409, detail="A campaign that was sent cannot change status"
            )

        if payload.name is not None:
            campaign.name = payload.name
        if payload.subject is not None:
            campaign.subject = payload.subject
        if payload.preview_text is not None:
            campaign.preview_text = payload.preview_text
        if payload.channel is not None:
            campaign.channel = _validate_channel(payload.channel)
        if getattr(payload, "template_id", None) is not None or getattr(
            payload, "templateId", None
        ) is not None:
            campaign.template_id = _resolve_template(db, tenant_id, payload)
        list_keys = ("list_id", "listId", "list_ids", "listIds")
        if any(getattr(payload, key, None) is not None for key in list_keys):
            list_ids = _selected_list_ids(payload)
            _validate_list_ids(db, tenant_id, list_ids)
            campaign.list_ids = list_ids
            campaign.list_id = list_ids[0] if list_ids else None
        exclude_keys = ("exclude_list_ids", "excludeListIds")
        if any(getattr(payload, key, None) is not None for key in exclude_keys):
            excluded_ids = _excluded_list_ids(payload)
            _validate_list_ids(db, tenant_id, excluded_ids)
            campaign.exclude_list_ids = excluded_ids
        if any(getattr(payload, key, None) is not None for key in list_keys + exclude_keys):
            campaign.total_recipients = _audience_query(
                db,
                tenant_id,
                list(campaign.list_ids or []),
                list(campaign.exclude_list_ids or []),
            ).count()
        if payload.campaign_type is not None or payload.campaignType is not None:
            campaign.campaign_type = _validate_campaign_type(
                payload.campaign_type or payload.campaignType
            )
        if payload.timezone is not None:
            campaign.timezone = payload.timezone
        if getattr(payload, "ab_test_id", None) is not None or getattr(
            payload, "abTestId", None
        ) is not None:
            campaign.ab_test_id = _resolve_ab_test(db, tenant_id, payload)
        # Changing the sender is only meaningful before the campaign goes out.
        if campaign.status not in ("sent", "sending"):
            sender_keys = ("alias_id", "aliasId", "from_email", "fromEmail")
            if any(getattr(payload, key, None) is not None for key in sender_keys):
                from_email, from_name = _resolve_sender(db, tenant_id, payload)
                campaign.from_email = from_email
                campaign.from_name = from_name
        if payload.status is not None:
            campaign.status = _validate_status(payload.status)
        scheduled = _scheduled_value(payload)
        if scheduled is not None:
            campaign.scheduled_at = scheduled
            if campaign.status == "draft":
                campaign.status = "scheduled"

        db.commit()
        db.refresh(campaign)
        return _to_out(db, campaign, tenant_id)
    finally:
        db.close()


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Delete a campaign. Drafts already produced for it are kept."""
    db = SessionLocal()
    try:
        campaign = _get_campaign(db, campaign_id, tenant_id)
        db.delete(campaign)
        db.commit()
        return {"message": "Campaign deleted", "id": campaign_id}
    finally:
        db.close()


@router.post("/{campaign_id}/duplicate", response_model=CampaignOut, status_code=201)
def duplicate_campaign(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Copy a campaign as a fresh draft, the way Brevo's duplicate action does."""
    db = SessionLocal()
    try:
        original = _get_campaign(db, campaign_id, tenant_id)
        candidate = f"{original.name} (Copy)"
        suffix = 2
        while (
            db.query(Campaign.id)
            .filter(
                Campaign.tenant_id == tenant_id,
                Campaign.name == candidate,
            )
            .first()
        ):
            candidate = f"{original.name} (Copy {suffix})"
            suffix += 1

        copy = Campaign(
            tenant_id=tenant_id,
            name=candidate,
            subject=original.subject,
            preview_text=original.preview_text,
            channel=original.channel,
            status="draft",
            template_id=original.template_id,
            list_id=original.list_id,
            list_ids=list(original.list_ids or []),
            exclude_list_ids=list(original.exclude_list_ids or []),
            campaign_type=original.campaign_type or "marketing",
            timezone=original.timezone,
            ab_test_id=original.ab_test_id,
            total_recipients=_audience_query(
                db,
                tenant_id,
                list(original.list_ids or ([original.list_id] if original.list_id else [])),
                list(original.exclude_list_ids or []),
            ).count(),
            from_email=original.from_email,
            from_name=original.from_name,
        )
        db.add(copy)
        db.commit()
        db.refresh(copy)
        return _to_out(db, copy, tenant_id)
    finally:
        db.close()


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
def pause_campaign(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        campaign = _get_campaign(db, campaign_id, tenant_id)
        if campaign.status not in {"draft", "scheduled", "sending"}:
            raise HTTPException(
                status_code=409,
                detail=f"A {campaign.status} campaign cannot be paused",
            )
        campaign.status = "paused"
        db.commit()
        db.refresh(campaign)
        return _to_out(db, campaign, tenant_id)
    finally:
        db.close()


@router.post("/{campaign_id}/cancel", response_model=CampaignOut)
def cancel_campaign(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        campaign = _get_campaign(db, campaign_id, tenant_id)
        if campaign.status in {"sent", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"A {campaign.status} campaign cannot be cancelled",
            )
        campaign.status = "cancelled"
        db.commit()
        db.refresh(campaign)
        return _to_out(db, campaign, tenant_id)
    finally:
        db.close()


@router.get("/{campaign_id}/stats")
def campaign_stats(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Per-campaign counters plus the small summary the listing renders."""
    db = SessionLocal()
    try:
        campaign = _get_campaign(db, campaign_id, tenant_id)
        out = _to_out(db, campaign, tenant_id)
        return {
            "campaign": out.model_dump(mode="json"),
            "stats": {
                "total_recipients": out.total_recipients,
                "delivered": out.delivered,
                "opened": out.opened,
                "clicked": out.clicked,
                "replied": out.replied,
                "bounced": out.bounced,
                "unsubscribed": out.unsubscribed,
                "open_rate": out.open_rate,
                "click_rate": out.click_rate,
            },
        }
    finally:
        db.close()


@router.get("/{campaign_id}/analytics")
def campaign_analytics(campaign_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Brevo-style campaign report: counters, rates, devices and A/B results.

    Counters come from the campaign row (which the send path keeps current)
    while device and geography are derived from the tracking events recorded for
    this campaign's drafts, so the report never claims data it does not have.
    """
    db = SessionLocal()
    try:
        campaign = _get_campaign(db, campaign_id, tenant_id)
        out = _to_out(db, campaign, tenant_id)

        draft_ids = [
            row[0]
            for row in db.query(Draft.id).filter(
                Draft.tenant_id == tenant_id, Draft.campaign_id == campaign.id
            )
        ]
        events = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant_id,
                Event.event_type.in_(["email_opened", "link_clicked"]),
            )
            .all()
            if draft_ids
            else []
        )
        events = [
            event for event in events if (event.data or {}).get("draft_id") in draft_ids
        ]

        devices: Dict[str, int] = {}
        countries: Dict[str, int] = {}
        for event in events:
            data = event.data or {}
            device = str(data.get("device") or "unknown")
            devices[device] = devices.get(device, 0) + 1
            country = str(data.get("country") or "unknown")
            countries[country] = countries.get(country, 0) + 1

        ab_results = None
        if campaign.ab_test_id is not None:
            from app.db import ABTest
            from app.services.abtesting import test_results

            test = (
                db.query(ABTest)
                .filter(
                    ABTest.id == campaign.ab_test_id,
                    ABTest.tenant_id == tenant_id,
                )
                .first()
            )
            if test is not None:
                ab_results = test_results(db, test)

        return {
            "campaign": out.model_dump(mode="json"),
            "stats": {
                "total_recipients": out.total_recipients,
                "delivered": out.delivered,
                "opened": out.opened,
                "clicked": out.clicked,
                "replied": out.replied,
                "bounced": out.bounced,
                "unsubscribed": out.unsubscribed,
                "spam_complaints": out.spam_complaints,
                "open_rate": out.open_rate,
                "click_rate": out.click_rate,
            },
            "devices": devices,
            "countries": countries,
            "ab_test": ab_results,
        }
    finally:
        db.close()


class AudiencePreviewRequest(BaseModel):
    list_ids: Optional[List[int]] = None
    listIds: Optional[List[int]] = None
    exclude_list_ids: Optional[List[int]] = None
    excludeListIds: Optional[List[int]] = None


@router.post("/audience/preview")
def preview_audience(
    payload: AudiencePreviewRequest, tenant_id: int = Depends(current_tenant_id)
):
    """Live recipient estimate and per-list breakdown for the campaign wizard.

    Exposes the overlap too: someone in two selected lists is one recipient, not
    two, which is the number Brevo shows in its audience step.
    """
    db = SessionLocal()
    try:
        list_ids = _selected_list_ids(payload)
        excluded_ids = _excluded_list_ids(payload)
        _validate_list_ids(db, tenant_id, list_ids + excluded_ids)

        per_list: List[Dict[str, object]] = []
        member_sets: Dict[int, set] = {}
        for list_id in list_ids:
            ids = {
                row[0]
                for row in _audience_query(db, tenant_id, [list_id], [])
                .with_entities(Contact.id)
                .all()
            }
            member_sets[list_id] = ids
            name = (
                db.query(ContactList.name)
                .filter(
                    ContactList.id == list_id, ContactList.tenant_id == tenant_id
                )
                .scalar()
            )
            per_list.append({"id": list_id, "name": name, "eligible": len(ids)})

        overlap = 0
        if len(member_sets) > 1:
            combined = set().union(*member_sets.values())
            overlap = sum(len(ids) for ids in member_sets.values()) - len(combined)

        total = _audience_query(db, tenant_id, list_ids, excluded_ids).count()
        return {
            "total_recipients": total,
            "per_list": per_list,
            "overlap": overlap,
            "excluded_lists": excluded_ids,
        }
    finally:
        db.close()


@router.get("/audience/overlap")
def audience_overlap(tenant_id: int = Depends(current_tenant_id)):
    """Lists that share contacts, so a send is not duplicated across them."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ContactListMember.list_id, ContactListMember.contact_id)
            .filter(ContactListMember.tenant_id == tenant_id)
            .all()
        )
        contact_lists: Dict[int, set] = {}
        for list_id, contact_id in rows:
            contact_lists.setdefault(contact_id, set()).add(list_id)

        duplicates: Dict[tuple, int] = {}
        for list_ids in contact_lists.values():
            ordered = sorted(list_ids)
            for index, first in enumerate(ordered):
                for second in ordered[index + 1 :]:
                    duplicates[(first, second)] = duplicates.get((first, second), 0) + 1

        names = {
            row[0]: row[1]
            for row in db.query(ContactList.id, ContactList.name).filter(
                ContactList.tenant_id == tenant_id
            )
        }
        overlaps = [
            {
                "list_a": pair[0],
                "list_b": pair[1],
                "list_a_name": names.get(pair[0]),
                "list_b_name": names.get(pair[1]),
                "shared_contacts": count,
            }
            for pair, count in sorted(
                duplicates.items(), key=lambda item: item[1], reverse=True
            )
        ]
        return {"overlaps": overlaps}
    finally:
        db.close()

