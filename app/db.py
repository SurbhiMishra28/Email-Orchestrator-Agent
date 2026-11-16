"""Database connection and session management."""
import os
import logging
from sqlalchemy import create_engine, event, text, ForeignKey, inspect
from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column
from sqlalchemy.types import (
    TypeDecorator,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    Float,
    JSON,
)
from datetime import datetime, timezone
from typing import Optional, List, Any
from contextlib import contextmanager

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

# DATABASE_URL is loaded from the project .env by app.config; default to SQLite.
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./email_orchestrator.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UTCDateTime(TypeDecorator):
    """Store naive UTC in the database and return timezone-aware UTC values.

    Both SQLite and MySQL drop tzinfo, so without this every timestamp was
    serialized without an offset and browsers displayed it as local time.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Contact(Base):
    __tablename__ = "contacts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    company: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[Optional[str]] = mapped_column(String(255))
    industry: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(100))
    linkedin: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    eligible_to_email: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Draft(Base):
    __tablename__ = "drafts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft, sent, failed
    variables: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contacts.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100))  # email_opened, link_clicked, reply_received
    data: Mapped[dict] = mapped_column(JSON, default={})
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class Log(Base):
    __tablename__ = "logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(20), default="info")
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ToolUse(Base):
    __tablename__ = "tool_uses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict] = mapped_column(JSON, default={})
    result: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class Template(Base):
    __tablename__ = "templates"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), default="intro")
    subject_template: Mapped[str] = mapped_column(String(500))
    body_template: Mapped[str] = mapped_column(Text)
    variables: Mapped[dict] = mapped_column(JSON, default={})
    tags: Mapped[list] = mapped_column(JSON, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SMTPConfig(Base):
    __tablename__ = "smtp_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host: Mapped[Optional[str]] = mapped_column(String(255), default=app_settings.DEFAULT_SMTP_HOST)
    port: Mapped[int] = mapped_column(Integer, default=app_settings.DEFAULT_SMTP_PORT)
    user: Mapped[Optional[str]] = mapped_column(String(255), default=app_settings.DEFAULT_SMTP_USER)
    password: Mapped[Optional[str]] = mapped_column(String(255), default=app_settings.DEFAULT_SMTP_PASSWORD)
    sender: Mapped[Optional[str]] = mapped_column(String(255), default=app_settings.DEFAULT_SMTP_SENDER)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    authentication_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Settings(Base):
    __tablename__ = "settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal: Mapped[str] = mapped_column(String(500), default=app_settings.DEFAULT_GOAL)
    business_name: Mapped[str] = mapped_column(String(255), default=app_settings.DEFAULT_BUSINESS_NAME)
    business_offer: Mapped[str] = mapped_column(String(500), default=app_settings.DEFAULT_BUSINESS_OFFER)
    daily_cap: Mapped[int] = mapped_column(Integer, default=app_settings.DEFAULT_DAILY_CAP)
    domain_cap: Mapped[int] = mapped_column(Integer, default=app_settings.DEFAULT_DOMAIN_CAP)
    AUTO_APPROVE: Mapped[bool] = mapped_column(Boolean, default=app_settings.DEFAULT_AUTO_APPROVE)
    AUTOPILOT: Mapped[bool] = mapped_column(Boolean, default=app_settings.DEFAULT_AUTOPILOT)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contacts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="not_checked")  # not_checked, deliverable, undeliverable, risky, inconclusive
    smtp_check: Mapped[str] = mapped_column(String(50), default="not_checked")
    mx_check: Mapped[str] = mapped_column(String(50), default="not_checked")
    catch_all: Mapped[bool] = mapped_column(Boolean, default=False)
    disposable: Mapped[bool] = mapped_column(Boolean, default=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    last_checked: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    sender: Mapped[Optional[str]] = mapped_column(String(320))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    snippet: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(timezone.utc)
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class ReplyProcessed(Base):
    """Track which replies have been auto-processed to prevent duplicates."""
    __tablename__ = "replies_processed"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_uid: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class VerificationJob(Base):
    __tablename__ = "verification_jobs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, running, completed, failed
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    deliverable: Mapped[int] = mapped_column(Integer, default=0)
    undeliverable: Mapped[int] = mapped_column(Integer, default=0)
    risky: Mapped[int] = mapped_column(Integer, default=0)
    inconclusive: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Create tables
def init_db():
    """Initialize database tables and add columns that create_all cannot."""
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns():
    """Additive, idempotent upgrades for databases created by older models."""
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        # Check draft table for error_message column
        if "drafts" in table_names:
            columns = {column["name"] for column in inspector.get_columns("drafts")}
            if "error_message" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE drafts ADD COLUMN error_message TEXT NULL")
                    )
                logger.info("Added missing drafts.error_message column")
        
        # Check smtp_config for authentication_configured column
        if "smtp_config" in table_names:
            columns = {column["name"] for column in inspector.get_columns("smtp_config")}
            if "authentication_configured" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE smtp_config ADD COLUMN "
                            "authentication_configured BOOLEAN DEFAULT 0"
                        )
                    )
                logger.info("Added missing smtp_config.authentication_configured column")
        
        # Check inbox_messages for processed and processed_at columns
        if "inbox_messages" in table_names:
            columns = {column["name"] for column in inspector.get_columns("inbox_messages")}
            if "processed" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE inbox_messages ADD COLUMN processed BOOLEAN DEFAULT 0")
                    )
                logger.info("Added missing inbox_messages.processed column")
            if "processed_at" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE inbox_messages ADD COLUMN processed_at DATETIME NULL")
                    )
                logger.info("Added missing inbox_messages.processed_at column")
        
        # Check for replies_processed table (created by new model)
        if "replies_processed" not in table_names:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE replies_processed ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "message_uid VARCHAR(100) NOT NULL UNIQUE, "
                        "contact_id INTEGER NULL, "
                        "processed_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                        ")"
                    )
                )
            logger.info("Created missing replies_processed table")
    except Exception as exc:  # never block startup on a best-effort upgrade
        logger.warning("Schema column check failed: %s", exc)


@contextmanager
def get_db():
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()