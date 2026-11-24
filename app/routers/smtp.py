"""Per-tenant SMTP configuration API router."""
from fastapi import APIRouter, Depends, HTTPException

from app.db import Log, SMTPConfig, SessionLocal
from app.deps import current_tenant_id
from app.models.schemas import SMTPConfigBase, SMTPConfigOut
from app.services.mailer import (
    SMTPConfigView,
    active_transport,
    environment_config,
    is_configured,
    resolve_smtp_config,
    test_connection,
)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_or_create_config(db, tenant_id: int) -> SMTPConfig:
    config = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == tenant_id).first()
    if not config:
        config = SMTPConfig(tenant_id=tenant_id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get("/status", response_model=SMTPConfigOut)
def get_smtp_status(tenant_id: int = Depends(current_tenant_id)):
    """Report the mailbox used for sending.

    A blank database row is completed from the environment for the local
    single-user tenant, so the dashboard shows the mailbox that will actually be
    used instead of claiming nothing is configured.
    """
    db = SessionLocal()
    try:
        view = resolve_smtp_config(db, tenant_id)
        return SMTPConfigOut(
            host=view.host or None,
            port=view.port,
            user=view.user or None,
            password=None,  # Never return the password
            sender=view.sender or None,
            configured=is_configured(view),
            authentication_configured=(
                view.authentication_configured
                or (active_transport() == "gmail_api" and is_configured(view))
            ),
            source=view.source,
            transport=active_transport(),
        )
    finally:
        db.close()


@router.post("/config")
def save_smtp_config(
    config: SMTPConfigBase,
    tenant_id: int = Depends(current_tenant_id),
):
    """Save the tenant's SMTP settings."""
    db = SessionLocal()
    try:
        if config.port is not None and not 1 <= config.port <= 65535:
            raise HTTPException(status_code=422, detail="SMTP port must be between 1 and 65535")

        existing = _get_or_create_config(db, tenant_id)

        existing.host = (config.host or "").strip() or None
        existing.port = config.port or 587
        existing.user = (config.user or "").strip() or None
        existing.sender = (config.sender or "").strip() or None
        # A blank password means "keep the saved one" rather than clearing it.
        if config.password:
            existing.password = config.password
        existing.configured = bool(existing.host and (existing.sender or existing.user))
        existing.authentication_configured = bool(existing.user and existing.password)

        db.add(
            Log(
                message=f"SMTP config saved: {'configured' if existing.configured else 'not configured'}",
                level="info",
                tenant_id=tenant_id,
            )
        )
        db.commit()

        return {
            "message": "SMTP configuration saved",
            "configured": existing.configured,
            "authentication_configured": existing.authentication_configured,
        }
    finally:
        db.close()


@router.post("/test")
def test_smtp_config(
    config: SMTPConfigBase,
    tenant_id: int = Depends(current_tenant_id),
):
    """Test SMTP connectivity, falling back to saved (or environment) values.

    The dashboard posts blank inputs when it only wants to re-check what is
    stored, so every field is filled from the resolved mailbox first.
    """
    db = SessionLocal()
    try:
        resolved = resolve_smtp_config(db, tenant_id)
    finally:
        db.close()

    if active_transport() == "gmail_api":
        candidate = resolved
    else:
        candidate = SMTPConfigView(
            host=config.host or resolved.host,
            port=config.port or resolved.port,
            user=config.user or resolved.user,
            password=config.password or resolved.password,
            sender=config.sender or resolved.sender,
            source=resolved.source,
        )

    if active_transport() == "gmail_api" and not is_configured(candidate):
        result = {
            "ok": False,
            "message": "Gmail API is not configured for this workspace.",
        }
    else:
        result = test_connection(
            candidate.host,
            candidate.port,
            candidate.user or None,
            candidate.password or None,
        )
    result["configured"] = is_configured(candidate)
    result["source"] = resolved.source
    result["host"] = candidate.host
    result["port"] = candidate.port
    result["transport"] = active_transport()
    return result


@router.get("/defaults")
def smtp_defaults(tenant_id: int = Depends(current_tenant_id)):
    """Describe the environment mailbox without leaking its password.

    Lets an operator see that a deployment has credentials available and offers
    them as a one-click fill-in for the tenant's own row.
    """
    env = environment_config()
    return {
        "available": bool(env.host),
        "host": env.host or None,
        "port": env.port,
        "user": env.user or None,
        "sender": env.sender or None,
        "authentication_configured": env.authentication_configured,
        "transport": active_transport(),
    }
