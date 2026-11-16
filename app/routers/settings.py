"""Settings API router."""
from fastapi import APIRouter

from app.db import SessionLocal, Settings, Log
from app.models.schemas import SettingsUpdate, SettingsOut
from app.config import settings as app_settings

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=SettingsOut)
def get_settings():
    db = SessionLocal()
    try:
        settings = db.query(Settings).first()
        if not settings:
            # Create default settings
            settings = Settings(
                goal=app_settings.DEFAULT_GOAL,
                business_name=app_settings.DEFAULT_BUSINESS_NAME,
                business_offer=app_settings.DEFAULT_BUSINESS_OFFER
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        return SettingsOut.model_validate(settings)
    finally:
        db.close()


@router.post("", response_model=SettingsOut)
def update_settings(settings: SettingsUpdate):
    db = SessionLocal()
    try:
        db_settings = db.query(Settings).first()
        
        if not db_settings:
            db_settings = Settings()
            db.add(db_settings)
        
        for field, value in settings.model_dump(exclude_unset=True).items():
            setattr(db_settings, field, value)
        
        db.commit()
        db.refresh(db_settings)
        
        log = Log(message=f"Settings updated", level="info")
        db.add(log)
        db.commit()
        
        return SettingsOut.model_validate(db_settings)
    finally:
        db.close()