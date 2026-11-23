"""Inbox API router (IMAP, tenant-scoped)."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db import IMAPConfig, InboxMessage, Log, SessionLocal
from app.deps import current_tenant_id
from app.models.schemas import IMAPConfigBase, IMAPConfigOut
from app.services.inbox import (
    IMAPConfigView,
    InboxError,
    InboxNotConfigured,
    environment_config,
    resolve_imap_config,
    sync_inbox,
    test_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
def list_inbox(limit: int = 50, tenant_id: int = Depends(current_tenant_id)):
    """Return the tenant's stored inbox messages plus whether IMAP is configured."""
    db = SessionLocal()
    try:
        view = resolve_imap_config(db, tenant_id)
        messages = (
            db.query(InboxMessage)
            .filter(InboxMessage.tenant_id == tenant_id)
            .order_by(InboxMessage.received_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return {
            "configured": view.configured,
            "source": view.source,
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


@router.get("/status", response_model=IMAPConfigOut)
def get_inbox_status(tenant_id: int = Depends(current_tenant_id)):
    """Report the mailbox used for reply polling (never the password)."""
    db = SessionLocal()
    try:
        view = resolve_imap_config(db, tenant_id)
        return IMAPConfigOut(
            host=view.host or None,
            port=view.port,
            user=view.user or None,
            folder=view.folder,
            configured=view.configured,
            source=view.source,
        )
    finally:
        db.close()


@router.post("/config")
def save_inbox_config(
    config: IMAPConfigBase,
    tenant_id: int = Depends(current_tenant_id),
):
    """Save the tenant's IMAP settings.

    A blank password keeps the stored one, mirroring SMTP, so the dashboard can
    re-save the other fields without the operator retyping the app password.
    """
    db = SessionLocal()
    try:
        if config.port is not None and not 1 <= config.port <= 65535:
            raise HTTPException(status_code=422, detail="IMAP port must be between 1 and 65535")

        row = db.query(IMAPConfig).filter(IMAPConfig.tenant_id == tenant_id).first()
        if not row:
            row = IMAPConfig(tenant_id=tenant_id)
            db.add(row)

        row.host = (config.host or "").strip() or None
        row.port = config.port or 993
        row.user = (config.user or "").strip() or None
        row.folder = (config.folder or "INBOX").strip() or "INBOX"
        if config.password:
            row.password = config.password
        row.configured = bool(row.host and row.user and row.password)

        db.add(
            Log(
                message=f"IMAP config saved: {'configured' if row.configured else 'not configured'}",
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()

        return {
            "message": "IMAP configuration saved",
            "configured": row.configured,
        }
    finally:
        db.close()


@router.post("/test")
def test_inbox_config(
    config: IMAPConfigBase | None = None,
    tenant_id: int = Depends(current_tenant_id),
):
    """Test IMAP connectivity, filling blanks from the resolved mailbox."""
    db = SessionLocal()
    try:
        resolved = resolve_imap_config(db, tenant_id)
    finally:
        db.close()

    candidate = IMAPConfigView(
        host=(config.host if config else None) or resolved.host,
        port=(config.port if config else None) or resolved.port,
        user=(config.user if config else None) or resolved.user,
        password=(config.password if config else None) or resolved.password,
        folder=(config.folder if config else None) or resolved.folder,
    )

    result = test_connection(candidate)
    result["configured"] = candidate.configured
    result["source"] = resolved.source
    result["host"] = candidate.host
    result["port"] = candidate.port
    return result


@router.get("/defaults")
def inbox_defaults(tenant_id: int = Depends(current_tenant_id)):
    """Describe the environment mailbox without leaking its password."""
    env = environment_config()
    return {
        "available": bool(env.host),
        "host": env.host or None,
        "port": env.port,
        "user": env.user or None,
        "folder": env.folder,
    }


@router.post("/sync")
def sync(limit: int = 25, tenant_id: int = Depends(current_tenant_id)):
    """Fetch the newest messages from IMAP and store ones not seen before."""
    db = SessionLocal()
    try:
        if not resolve_imap_config(db, tenant_id).configured:
            raise HTTPException(
                status_code=400,
                detail="IMAP is not configured. Add inbox settings in Settings first.",
            )
        try:
            result = sync_inbox(max(1, min(limit, 100)), tenant_id=tenant_id, db=db)
        except InboxNotConfigured as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except InboxError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"configured": True, **result}
    finally:
        db.close()
