"""Sending limits shared by manual sends and the queue.

Implements the documented daily cap, warm-up ramp, per-recipient-domain cap
and the pacing gap between sends. A blocked send never mutates the draft.

Every counter is scoped to one tenant: a busy account must not consume another
tenant's daily allowance or trigger its pacing delay.
"""
import os
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import func

from app.db import Contact, Draft, Settings, Tenant

# Daily ceiling for a single workspace. Ten per day is deliberate: it stays
# inside a consumer mailbox's comfortable range and keeps a cold thread from
# looking like a blast, while still being enough to work through a small list.
# ``DAILY_CAP`` overrides it per deployment; the default stays 10 so an
# unconfigured install is conservative.
DEFAULT_DAILY_CAP = 10
POST_WARMUP_CAP = DEFAULT_DAILY_CAP

# No warm-up ramp. The ramp exists to protect a brand-new sending domain, and
# this deployment sends from an established mailbox, so a flat cap is both
# simpler and matches what the operator asked for.
WARMUP_CAPS = ()

# Minimum gap between two sends. This is the knob that decides how fast a queue
# drains: at 60s a ten-contact workspace needs ten minutes and a single Run only
# ever sends one message, which reads as "nothing happened". Ten seconds still
# avoids an instant burst while letting a small batch finish inside one request.
# ``PACING_SECONDS`` overrides it per deployment.
DEFAULT_PACING_SECONDS = 10


def _env_int(name: str, default: int) -> int:
    """Parse a positive integer setting, falling back to ``default``."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Read once at import so ``.env`` and the process environment apply, while a
# test (or a caller that has a reason) can still rebind these module globals.
DAILY_CAP = _env_int("DAILY_CAP", POST_WARMUP_CAP)
PACING_SECONDS = _env_int("PACING_SECONDS", DEFAULT_PACING_SECONDS)


def hard_daily_cap() -> int:
    """The deployment-wide daily ceiling (``DAILY_CAP``, default 10)."""
    return DAILY_CAP


def pacing_seconds() -> int:
    """The minimum gap between two sends (``PACING_SECONDS``, default 10)."""
    return PACING_SECONDS


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
    """Cap for the current warm-up day, based on the first successful send.

    ``WARMUP_CAPS`` is empty, so this is the flat deployment ceiling. When a
    ramp is configured it still may never exceed ``DAILY_CAP``.
    """
    ceiling = hard_daily_cap()
    first = (
        _tenant_drafts(db, tenant_id)
        .with_entities(func.min(Draft.sent_at))
        .filter(Draft.status == "sent")
        .scalar()
    )
    first = _utc(first)
    if first is None:
        return ceiling
    now = now or datetime.now(timezone.utc)
    day = (now.date() - first.date()).days + 1
    for last_day, cap in WARMUP_CAPS:
        if day <= last_day:
            return min(cap, ceiling)
    return ceiling


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


def check_tenant_send_allowed(
    db,
    tenant_id: Optional[int],
    recipient_email: str = "",
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Return (allowed, human-readable reason when blocked).

    Takes the tenant directly instead of a ``Contact`` so every send path —
    including ones that only know a stored address — goes through the same
    gate. The effective daily cap is the lower of the tenant's plan allowance,
    its configured cap, and the current warm-up cap.
    """
    now = now or datetime.now(timezone.utc)
    settings_query = db.query(Settings)
    if tenant_id is not None:
        settings_query = settings_query.filter(Settings.tenant_id == tenant_id)
    settings = settings_query.first()

    configured_daily = settings.daily_cap if settings else hard_daily_cap()
    configured_domain = settings.domain_cap if settings else 3
    ceiling = configured_daily or hard_daily_cap()
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

    domain = (recipient_email or "").split("@")[-1].lower()
    domain_sent = sent_to_domain_today(db, domain, tenant_id, now)
    if configured_domain and domain_sent >= configured_domain:
        return False, (
            f"Domain cap reached for {domain} ({domain_sent}/{configured_domain} today)."
        )

    elapsed = seconds_since_last_send(db, tenant_id, now)
    gap = pacing_seconds()
    if elapsed is not None and elapsed < gap:
        wait = int(gap - elapsed) + 1
        return False, f"Pacing: wait {wait}s before the next send."

    return True, ""


def check_send_allowed(
    db, contact: Contact, now: Optional[datetime] = None
) -> Tuple[bool, str]:
    """Return (allowed, reason) for one more send to ``contact``.

    The tenant is taken from ``contact`` so callers cannot forget to scope it.
    """
    return check_tenant_send_allowed(
        db,
        getattr(contact, "tenant_id", None),
        getattr(contact, "email", "") or "",
        now,
    )
