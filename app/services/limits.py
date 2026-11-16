"""Sending limits shared by manual sends and the queue.

Implements the documented daily cap, warm-up ramp, per-recipient-domain cap
and 60-second pacing. A blocked send never mutates the draft.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import func

from app.db import Contact, Draft, Settings

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


def sent_today(db, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    return (
        db.query(Draft)
        .filter(Draft.status == "sent", Draft.sent_at >= start_of_day(now))
        .count()
    )


def sent_to_domain_today(db, domain: str, now: Optional[datetime] = None) -> int:
    if not domain:
        return 0
    now = now or datetime.now(timezone.utc)
    return (
        db.query(Draft)
        .join(Contact, Draft.contact_id == Contact.id)
        .filter(
            Draft.status == "sent",
            Draft.sent_at >= start_of_day(now),
            func.lower(Contact.email).like(f"%@{domain.lower()}"),
        )
        .count()
    )


def warmup_cap(db, now: Optional[datetime] = None) -> int:
    """Cap for the current warm-up day, based on the first successful send."""
    first = db.query(func.min(Draft.sent_at)).filter(Draft.status == "sent").scalar()
    first = _utc(first)
    if first is None:
        return POST_WARMUP_CAP
    now = now or datetime.now(timezone.utc)
    day = (now.date() - first.date()).days + 1
    for last_day, cap in WARMUP_CAPS:
        if day <= last_day:
            return cap
    return POST_WARMUP_CAP


def seconds_since_last_send(db, now: Optional[datetime] = None) -> Optional[float]:
    last = db.query(func.max(Draft.sent_at)).filter(Draft.status == "sent").scalar()
    last = _utc(last)
    if last is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - last).total_seconds()


def check_send_allowed(
    db, contact: Contact, now: Optional[datetime] = None
) -> Tuple[bool, str]:
    """Return (allowed, human-readable reason when blocked)."""
    now = now or datetime.now(timezone.utc)
    settings = db.query(Settings).first()

    configured_daily = settings.daily_cap if settings else POST_WARMUP_CAP
    configured_domain = settings.domain_cap if settings else 3
    effective_daily = min(configured_daily or POST_WARMUP_CAP, warmup_cap(db, now))

    today = sent_today(db, now)
    if today >= effective_daily:
        return False, (
            f"Daily sending cap reached ({today}/{effective_daily}). "
            "Try again tomorrow."
        )

    domain = (contact.email or "").split("@")[-1].lower()
    domain_sent = sent_to_domain_today(db, domain, now)
    if configured_domain and domain_sent >= configured_domain:
        return False, (
            f"Domain cap reached for {domain} ({domain_sent}/{configured_domain} today)."
        )

    elapsed = seconds_since_last_send(db, now)
    if elapsed is not None and elapsed < PACING_SECONDS:
        wait = int(PACING_SECONDS - elapsed) + 1
        return False, f"Pacing: wait {wait}s before the next send."

    return True, ""
