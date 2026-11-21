"""Usage metering for billing and plan enforcement.

Every metered action writes a ``UsageLog`` row so a tenant's consumption can be
reported and capped without re-deriving it from drafts and events. Writes are
best-effort: metering must never break a send that already succeeded.
"""
import logging
from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import func

from app.db import UsageLog

logger = logging.getLogger(__name__)

EMAILS_SENT = "emails_sent"
EMAILS_DRAFTED = "emails_drafted"
REPLIES_RECEIVED = "replies_received"


def record_usage(db, tenant_id: Optional[int], metric: str, quantity: int = 1) -> None:
    """Add a usage row to ``db`` without committing.

    The caller commits as part of its own transaction so a send and its usage
    row land together. ``tenant_id=None`` is ignored: usage is per tenant.
    """
    if tenant_id is None or quantity <= 0:
        return
    db.add(
        UsageLog(
            tenant_id=tenant_id,
            metric=metric,
            quantity=quantity,
            period="daily",
        )
    )


def usage_since(
    db, tenant_id: int, metric: str, since: datetime
) -> int:
    """Total quantity for ``metric`` recorded at or after ``since``."""
    total = (
        db.query(func.coalesce(func.sum(UsageLog.quantity), 0))
        .filter(
            UsageLog.tenant_id == tenant_id,
            UsageLog.metric == metric,
            UsageLog.created_at >= since,
        )
        .scalar()
    )
    return int(total or 0)


def usage_today(db, tenant_id: int, metric: str, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    return usage_since(
        db, tenant_id, metric, datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    )


def period_totals(db, tenant_id: int, now: Optional[datetime] = None) -> dict:
    """Today's and this month's totals for every tracked metric."""
    now = now or datetime.now(timezone.utc)
    day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    month_start = day_start.replace(day=1)

    month_rows = (
        db.query(UsageLog.metric, func.sum(UsageLog.quantity))
        .filter(UsageLog.tenant_id == tenant_id, UsageLog.created_at >= month_start)
        .group_by(UsageLog.metric)
        .all()
    )
    day_rows = (
        db.query(UsageLog.metric, func.sum(UsageLog.quantity))
        .filter(UsageLog.tenant_id == tenant_id, UsageLog.created_at >= day_start)
        .group_by(UsageLog.metric)
        .all()
    )
    month = {metric: int(total or 0) for metric, total in month_rows}
    today = {metric: int(total or 0) for metric, total in day_rows}

    metrics = (EMAILS_SENT, EMAILS_DRAFTED, REPLIES_RECEIVED)
    return {
        "today": {metric: today.get(metric, 0) for metric in metrics},
        "month": {metric: month.get(metric, 0) for metric in metrics},
    }
