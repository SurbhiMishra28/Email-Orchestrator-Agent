"""Sending limits shared by manual sends and the queue.

Implements the documented daily cap, warm-up ramp, per-recipient-domain cap
and 60-second pacing. A blocked send never mutates the draft.

Every counter is scoped to one tenant: a busy account must not consume another
tenant's daily allowance or trigger its pacing delay.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import func

from app.db import Contact, Draft, Settings, Tenant

# README: 5/day on days 1-3, 10 on 4-7, 30 on 8-14, 50 thereafter.
WARMUP_CAPS = ((3, 5), (7, 10), (14, 30))
POST_WARMUP_CAP = 50
PACING_SECONDS = 60


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def start_of_day(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


def _tenant_drafts(db, tenant_id: Optional[int]):
    query = db.query(Draft)
    if tenant_id is not None:
        query = query.filter(Draft.tenant_id == tenant_id)
    return query


def sent_today(db, tenant_id: Optional[int] = None, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    return (
        _tenant_drafts(db, tenant_id)
        .filter(Draft.status == "sent", Draft.sent_at >= start_of_day(now))
        .count()
    )


def sent_to_domain_today(
    db, domain: str, tenant_id: Optional[int] = None, now: Optional[datetime] = None
) -> int:
    if not domain:
        return 0
    now = now or datetime.now(timezone.utc)
    query = _tenant_drafts(db, tenant_id).join(Contact, Draft.contact_id == Contact.id)
    return (
        query.filter(
            Draft.status == "sent",
            Draft.sent_at >= start_of_day(now),
            func.lower(Contact.email).like(f"%@{domain.lower()}"),
        )
        .count()
    )


def warmup_cap(db, tenant_id: Optional[int] = None, now: Optional[datetime] = None) -> int:
    """Cap for the current warm-up day, based on the first successful send."""
    first = (
        _tenant_drafts(db, tenant_id)
        .with_entities(func.min(Draft.sent_at))
        .filter(Draft.status == "sent")
        .scalar()
    )
    first = _utc(first)
    if first is None:
        return POST_WARMUP_CAP
    now = now or datetime.now(timezone.utc)
    day = (now.date() - first.date()).days + 1
    for last_day, cap in WARMUP_CAPS:
        if day <= last_day:
            return cap
    return POST_WARMUP_CAP


def seconds_since_last_send(
    db, tenant_id: Optional[int] = None, now: Optional[datetime] = None
) -> Optional[float]:
    last = (
        _tenant_drafts(db, tenant_id)
        .with_entities(func.max(Draft.sent_at))
        .filter(Draft.status == "sent")
        .scalar()
    )
    last = _utc(last)
    if last is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - last).total_seconds()


def plan_daily_limit(db, tenant_id: Optional[int]) -> Optional[int]:
    """The tenant's plan allowance, or ``None`` when it is unlimited/unset."""
    if tenant_id is None:
        return None
    limit = (
        db.query(Tenant.daily_email_limit)
        .filter(Tenant.id == tenant_id)
        .scalar()
    )
    if not limit or limit <= 0:
        return None
    return int(limit)


def check_send_allowed(
    db, contact: Contact, now: Optional[datetime] = None
) -> Tuple[bool, str]:
    """Return (allowed, human-readable reason when blocked).

    The tenant is taken from ``contact`` so callers cannot forget to scope it.
    The effective daily cap is the lower of the tenant's plan allowance, its
    configured cap, and the current warm-up cap.
    """
    now = now or datetime.now(timezone.utc)
    tenant_id = getattr(contact, "tenant_id", None)
    settings_query = db.query(Settings)
    if tenant_id is not None:
        settings_query = settings_query.filter(Settings.tenant_id == tenant_id)
    settings = settings_query.first()

    configured_daily = settings.daily_cap if settings else POST_WARMUP_CAP
    configured_domain = settings.domain_cap if settings else 3
    ceiling = configured_daily or POST_WARMUP_CAP
    plan_limit = plan_daily_limit(db, tenant_id)
    if plan_limit is not None:
        ceiling = min(ceiling, plan_limit)
    effective_daily = min(ceiling, warmup_cap(db, tenant_id, now))

    today = sent_today(db, tenant_id, now)
    if today >= effective_daily:
        blocked_by_plan = plan_limit is not None and plan_limit <= ceiling
        detail = (
            f"Plan limit reached ({today}/{effective_daily}). Upgrade the plan to send more."
            if blocked_by_plan
            else f"Daily sending cap reached ({today}/{effective_daily}). Try again tomorrow."
        )
        return False, detail

    domain = (contact.email or "").split("@")[-1].lower()
    domain_sent = sent_to_domain_today(db, domain, tenant_id, now)
    if configured_domain and domain_sent >= configured_domain:
        return False, (
            f"Domain cap reached for {domain} ({domain_sent}/{configured_domain} today)."
        )

    elapsed = seconds_since_last_send(db, tenant_id, now)
    if elapsed is not None and elapsed < PACING_SECONDS:
        wait = int(PACING_SECONDS - elapsed) + 1
        return False, f"Pacing: wait {wait}s before the next send."

    return True, ""
