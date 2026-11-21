"""Inbox API router (IMAP, tenant-scoped)."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db import InboxMessage, SessionLocal
from app.deps import current_tenant_id
from app.services.inbox import InboxError, InboxNotConfigured, is_configured, sync_inbox

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
def list_inbox(limit: int = 50, tenant_id: int = Depends(current_tenant_id)):
    """Return the tenant's stored inbox messages plus whether IMAP is configured."""
    db = SessionLocal()
    try:
        messages = (
            db.query(InboxMessage)
            .filter(InboxMessage.tenant_id == tenant_id)
            .order_by(InboxMessage.received_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return {
            "configured": is_configured(),
            "messages": [
                {
                    "id": m.id,
                    "sender": m.sender,
                    "subject": m.subject,
                    "snippet": m.snippet,
                    "received_at": m.received_at.isoformat() if m.received_at else None,
                }
                for m in messages
            ],
        }
    finally:
        db.close()


@router.post("/sync")
def sync(limit: int = 25, tenant_id: int = Depends(current_tenant_id)):
    """Fetch the newest messages from IMAP and store ones not seen before."""
    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail="IMAP is not configured. Set IMAP_HOST, IMAP_USER and IMAP_PASS.",
        )
    try:
        result = sync_inbox(max(1, min(limit, 100)), tenant_id=tenant_id)
    except InboxNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"configured": True, **result}
