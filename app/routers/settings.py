"""Per-tenant Settings API router."""
from fastapi import APIRouter, Depends

from app.db import SessionLocal, Settings, Log
from app.deps import current_tenant_id
from app.models.schemas import SettingsUpdate, SettingsOut
from app.config import settings as app_settings

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_settings(db, tenant_id: int) -> Settings:
    """Fetch the tenant's settings row, creating a default one on first use."""
    settings = db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
    if not settings:
        settings = Settings(
            tenant_id=tenant_id,
            goal=app_settings.DEFAULT_GOAL,
            business_name=app_settings.DEFAULT_BUSINESS_NAME,
            business_offer=app_settings.DEFAULT_BUSINESS_OFFER,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("", response_model=SettingsOut)
def get_settings(tenant_id: int = Depends(current_tenant_id)):
    db = SessionLocal()
    try:
        return SettingsOut.model_validate(get_or_create_settings(db, tenant_id))
    finally:
        db.close()


@router.post("", response_model=SettingsOut)
def update_settings(
    settings: SettingsUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    db = SessionLocal()
    try:
        db_settings = get_or_create_settings(db, tenant_id)
        
        for field, value in settings.model_dump(exclude_unset=True).items():
            setattr(db_settings, field, value)
        
        db.commit()
        db.refresh(db_settings)
        
        db.add(Log(message="Settings updated", level="info", tenant_id=tenant_id))
        db.commit()
        
        return SettingsOut.model_validate(db_settings)
    finally:
        db.close()
