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
    scheduled_at: Optional[str] = None
    scheduledAt: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    subject: Optional[str] = Field(default=None, max_length=500)
    preview_text: Optional[str] = Field(default=None, max_length=500)
    channel: Optional[str] = None
    template_id: Optional[int] = None
    templateId: Optional[int] = None
    list_id: Optional[int] = None
    listId: Optional[int] = None
    status: Optional[str] = None
    scheduled_at: Optional[str] = None
    scheduledAt: Optional[str] = None


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
    list_name: Optional[str] = None
    template_name: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    total_recipients: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
    bounced: int = 0
    unsubscribed: int = 0
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


def _audience_size(db, tenant_id: int, list_id: Optional[int]) -> int:
    """Count the contacts a campaign would send to.

    A list campaign counts subscribed membership rows; a campaign with no list
    targets every eligible, non-blacklisted contact in the tenant.
    """
    if list_id is not None:
        return (
            db.query(func.count(ContactListMember.id))
            .join(Contact, Contact.id == ContactListMember.contact_id)
            .filter(
                ContactListMember.list_id == list_id,
                ContactListMember.tenant_id == tenant_id,
                ContactListMember.unsubscribed.isnot(True),
                Contact.tenant_id == tenant_id,
                Contact.eligible_to_email.is_(True),
                Contact.email_blacklisted.isnot(True),
            )
            .scalar()
            or 0
        )
    return (
        db.query(func.count(Contact.id))
        .filter(
            Contact.tenant_id == tenant_id,
            Contact.eligible_to_email.is_(True),
            Contact.email_blacklisted.isnot(True),
        )
        .scalar()
        or 0
    )


def _to_out(db, campaign: Campaign, tenant_id: int) -> CampaignOut:
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
        list_name=list_name,
        template_name=template_name,
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

    db = SessionLocal()
    try:
        template_id = _resolve_template(db, tenant_id, payload)
        list_id = _resolve_list(db, tenant_id, payload)

        campaign = Campaign(
            tenant_id=tenant_id,
            name=payload.name,
            subject=payload.subject,
            preview_text=payload.preview_text,
            channel=channel,
            status="scheduled" if scheduled_at else "draft",
            template_id=template_id,
            list_id=list_id,
            scheduled_at=scheduled_at,
            total_recipients=_audience_size(db, tenant_id, list_id),
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
        if getattr(payload, "list_id", None) is not None or getattr(
            payload, "listId", None
        ) is not None:
            campaign.list_id = _resolve_list(db, tenant_id, payload)
            campaign.total_recipients = _audience_size(db, tenant_id, campaign.list_id)
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
            total_recipients=_audience_size(db, tenant_id, original.list_id),
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
