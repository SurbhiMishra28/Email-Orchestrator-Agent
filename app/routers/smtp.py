"""SMTP configuration API router."""
from fastapi import APIRouter, HTTPException

from app.db import Log, SMTPConfig, SessionLocal
from app.models.schemas import SMTPConfigBase, SMTPConfigOut
from app.services.mailer import test_connection

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/status", response_model=SMTPConfigOut)
def get_smtp_status():
    db = SessionLocal()
    try:
        config = db.query(SMTPConfig).first()
        if not config:
            return SMTPConfigOut(
                host=None,
                port=587,
                user=None,
                password=None,
                sender=None,
                configured=False,
                authentication_configured=False,
            )

        return SMTPConfigOut(
            host=config.host,
            port=config.port,
            user=config.user,
            password=None,  # Never return the password
            sender=config.sender,
            configured=config.configured,
            authentication_configured=bool(getattr(config, "authentication_configured", False))
            or bool(config.user and config.password),
        )
    finally:
        db.close()


@router.post("/config")
def save_smtp_config(config: SMTPConfigBase):
    db = SessionLocal()
    try:
        if config.port is not None and not 1 <= config.port <= 65535:
            raise HTTPException(status_code=422, detail="SMTP port must be between 1 and 65535")

        existing = db.query(SMTPConfig).first()

        if existing:
            existing.host = (config.host or "").strip() or None
            existing.port = config.port or 587
            existing.user = (config.user or "").strip() or None
            existing.sender = (config.sender or "").strip() or None
            # A blank password means "keep the saved one" rather than clearing it.
            if config.password:
                existing.password = config.password
            existing.configured = bool(existing.host and (existing.sender or existing.user))
            existing.authentication_configured = bool(existing.user and existing.password)
        else:
            existing = SMTPConfig(
                host=(config.host or "").strip() or None,
                port=config.port or 587,
                user=(config.user or "").strip() or None,
                password=config.password or None,
                sender=(config.sender or "").strip() or None,
                configured=bool((config.host or "").strip()),
                authentication_configured=bool(config.user and config.password),
            )
            db.add(existing)

        db.add(
            Log(
                message=f"SMTP config saved: {'configured' if existing.configured else 'not configured'}",
                level="info",
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
def test_smtp_config(config: SMTPConfigBase):
    """Test SMTP connectivity, falling back to saved credentials for blanks."""
    db = SessionLocal()
    try:
        saved = db.query(SMTPConfig).first()
    finally:
        db.close()

    host = (config.host or (saved.host if saved else None) or "").strip()
    port = config.port or (saved.port if saved else 587)
    user = (config.user or (saved.user if saved else None) or "").strip() or None
    password = config.password or (saved.password if saved else None)

    return test_connection(host, port, user, password)
