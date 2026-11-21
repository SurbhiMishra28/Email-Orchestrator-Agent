"""Database connection and session management."""
import os
import logging
from sqlalchemy import create_engine, event, text, ForeignKey, UniqueConstraint, inspect
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

connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite")
    else {}
)
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
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    company: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[Optional[str]] = mapped_column(String(255))
    industry: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(100))
    linkedin: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    eligible_to_email: Mapped[bool] = mapped_column(Boolean, default=False)
    # Brevo keeps a separate per-channel blacklist next to the opt-in flag: a
    # contact can be subscribed but blacklisted after a hard bounce or a
    # complaint, and lists report those separately.
    email_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=[])
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ContactListFolder(Base):
    """A folder that groups lists, mirroring Brevo's folder > list hierarchy.

    Deleting a folder deletes its lists, but never the contacts in them.
    """

    __tablename__ = "contact_list_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_contact_list_folders_tenant_name"),
    )


class ContactList(Base):
    """A named segment of contacts, owned by one tenant.

    Lists are explicit membership rows rather than a tag convention so a
    contact can belong to many lists and removal never mutates the contact.
    """

    __tablename__ = "contact_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )
    folder_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact_list_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Per-list campaign settings, which Brevo lets a list override on its own.
    from_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    from_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reply_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    header: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    footer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_contact_lists_tenant_name"),
    )


class ContactListMember(Base):
    """Membership of a contact in a list.

    ``tenant_id`` is denormalised so a membership row can be scoped without a
    join, and the composite unique constraint makes adding a contact twice a
    no-op rather than a duplicate.
    """

    __tablename__ = "contact_list_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )
    list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contact_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Brevo tracks a list-level unsubscribe separately from the account-level
    # blacklist, so a contact can stay subscribed globally but out of one list.
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("list_id", "contact_id", name="uq_list_member"),
    )


class Campaign(Base):
    """One outbound campaign, mirroring Brevo's Campaigns listing.

    A campaign is a named send over a channel: it picks a list (or nothing, for
    ad-hoc sends), a template and an optional subject, then either sends now,
    is scheduled, or stays a draft. Delivery counters live on the row so the
    listing can show results without joining every draft.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    preview_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # email, sms, push, whatsapp — Brevo offers one campaign per channel.
    channel: Mapped[str] = mapped_column(String(50), default="email")
    # draft, scheduled, sending, sent, paused, cancelled
    status: Mapped[str] = mapped_column(String(50), default="draft")
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("templates.id"), nullable=True
    )
    list_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact_lists.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    delivered: Mapped[int] = mapped_column(Integer, default=0)
    opened: Mapped[int] = mapped_column(Integer, default=0)
    clicked: Mapped[int] = mapped_column(Integer, default=0)
    replied: Mapped[int] = mapped_column(Integer, default=0)
    bounced: Mapped[int] = mapped_column(Integer, default=0)
    unsubscribed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Draft(Base):
    __tablename__ = "drafts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id"), nullable=False)
    # Set when the draft was produced by a campaign, so stats can be grouped.
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contacts.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100))  # email_opened, link_clicked, reply_received
    data: Mapped[dict] = mapped_column(JSON, default={})
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ABTest(Base):
    """A named A/B experiment over one or more outbound variants."""

    __tablename__ = "ab_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    # active: variants are used by queue passes. paused: drafts keep their
    # variant, no new assignment happens. completed: results are frozen.
    status: Mapped[str] = mapped_column(String(50), default="active")
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("templates.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ABVariant(Base):
    """One message variant of an experiment, with its relative weight."""

    __tablename__ = "ab_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    ab_test_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ab_tests.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("ab_test_id", "label", name="uq_ab_variant_label"),
    )


# ============ SaaS Multi-Tenant Models ============

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(50), default="free")  # free, pro, enterprise
    daily_email_limit: Mapped[int] = mapped_column(Integer, default=50)
    api_key_limit: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")  # admin, user, member
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255))
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    permissions: Mapped[list] = mapped_column(JSON, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class TenantMember(Base):
    __tablename__ = "tenant_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="member")
    invited_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, paid, failed, refunded
    period_start: Mapped[datetime] = mapped_column(UTCDateTime)
    period_end: Mapped[datetime] = mapped_column(UTCDateTime)
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"))
    metric: Mapped[str] = mapped_column(String(100))  # emails_sent, emails_drafted, replies_received
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    period: Mapped[str] = mapped_column(String(20), default="daily")  # daily, monthly
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))


class Log(Base):
    __tablename__ = "logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(20), default="info")
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ToolUse(Base):
    __tablename__ = "tool_uses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict] = mapped_column(JSON, default={})
    result: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class Template(Base):
    __tablename__ = "templates"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), default="intro")
    subject_template: Mapped[str] = mapped_column(String(500))
    body_template: Mapped[str] = mapped_column(Text)
    footer_template: Mapped[str] = mapped_column(Text, default="")
    variables: Mapped[dict] = mapped_column(JSON, default={})
    tags: Mapped[list] = mapped_column(JSON, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SMTPConfig(Base):
    __tablename__ = "smtp_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
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
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    goal: Mapped[str] = mapped_column(String(500), default=app_settings.DEFAULT_GOAL)
    business_name: Mapped[str] = mapped_column(String(255), default=app_settings.DEFAULT_BUSINESS_NAME)
    business_offer: Mapped[str] = mapped_column(String(500), default=app_settings.DEFAULT_BUSINESS_OFFER)
    daily_cap: Mapped[int] = mapped_column(Integer, default=app_settings.DEFAULT_DAILY_CAP)
    domain_cap: Mapped[int] = mapped_column(Integer, default=app_settings.DEFAULT_DOMAIN_CAP)
    AUTO_APPROVE: Mapped[bool] = mapped_column(Boolean, default=app_settings.DEFAULT_AUTO_APPROVE)
    AUTOPILOT: Mapped[bool] = mapped_column(Boolean, default=app_settings.DEFAULT_AUTOPILOT)

    # Footer and sender signature configuration
    footer_text: Mapped[str] = mapped_column(Text, default="")
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    sender_role: Mapped[str] = mapped_column(String(255), default="")
    company_website: Mapped[str] = mapped_column(String(500), default="")
    calendly_url: Mapped[str] = mapped_column(String(500), default="")

    # Engagement tracking is strictly opt-in per tenant: when this is false no
    # pixel or wrapped link is ever added to outbound mail.
    tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
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
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
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
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    message_uid: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), index=True)


class VerificationJob(Base):
    __tablename__ = "verification_jobs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
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


def _ensure_tenant_columns(inspector, table_names):
    """Add ``tenant_id`` to resource tables and backfill legacy rows.

    Databases created before multi-tenancy have no ``tenant_id`` anywhere.
    The column is added as plain ``INTEGER NULL`` (a portable ALTER form) and
    existing rows are assigned to the first tenant so a single-tenant
    deployment keeps working after the upgrade.
    """
    tenant_tables = [
        "users",
        "contacts",
        "drafts",
        "events",
        "templates",
        "smtp_config",
        "settings",
        "email_verifications",
        "inbox_messages",
        "replies_processed",
        "verification_jobs",
        "logs",
        "tool_uses",
        "contact_lists",
        "contact_list_folders",
        "contact_list_members",
        "campaigns",
    ]

    pending = []
    for table in tenant_tables:
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "tenant_id" not in columns:
            pending.append(table)

    if not pending:
        return

    with engine.begin() as connection:
        for table in pending:
            try:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER NULL")
                )
                logger.info("Added missing %s.tenant_id column", table)
            except Exception as exc:
                logger.warning("Could not add tenant_id to %s: %s", table, exc)

        for table in pending:
            try:
                # ``CREATE INDEX IF NOT EXISTS`` is SQLite/Postgres only, so
                # rely on the exception path for MySQL/MariaDB instead.
                connection.execute(
                    text(f"CREATE INDEX ix_{table}_tenant_id ON {table} (tenant_id)")
                )
            except Exception:
                logger.debug("%s.tenant_id index already present", table)

        legacy_tenant = connection.execute(
            text("SELECT id FROM tenants ORDER BY id LIMIT 1")
        ).scalar()
        if legacy_tenant is not None:
            for table in pending:
                try:
                    connection.execute(
                        text(
                            f"UPDATE {table} SET tenant_id = :tid "
                            "WHERE tenant_id IS NULL"
                        ),
                        {"tid": legacy_tenant},
                    )
                except Exception as exc:
                    logger.warning("Could not backfill %s.tenant_id: %s", table, exc)
            logger.info(
                "Backfilled legacy rows to tenant %s", legacy_tenant
            )


def _ensure_columns():
    """Additive, idempotent upgrades for databases created by older models."""
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        _ensure_tenant_columns(inspector, table_names)


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

        # Check templates for footer_template column
        if "templates" in table_names:
            columns = {column["name"] for column in inspector.get_columns("templates")}
            if "footer_template" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE templates ADD COLUMN footer_template TEXT DEFAULT ''")
                    )
                logger.info("Added missing templates.footer_template column")

        # Check settings for footer and sender columns
        if "settings" in table_names:
            columns = {column["name"] for column in inspector.get_columns("settings")}
            missing_settings_cols = []
            if "footer_text" not in columns:
                missing_settings_cols.append("footer_text TEXT DEFAULT ''")
            if "sender_name" not in columns:
                missing_settings_cols.append("sender_name VARCHAR(255) DEFAULT ''")
            if "sender_role" not in columns:
                missing_settings_cols.append("sender_role VARCHAR(255) DEFAULT ''")
            if "company_website" not in columns:
                missing_settings_cols.append("company_website VARCHAR(500) DEFAULT ''")
            if "calendly_url" not in columns:
                missing_settings_cols.append("calendly_url VARCHAR(500) DEFAULT ''")
            if "tracking_enabled" not in columns:
                missing_settings_cols.append(
                    "tracking_enabled BOOLEAN DEFAULT 0"
                )

            if missing_settings_cols:
                with engine.begin() as connection:
                    for col in missing_settings_cols:
                        col_name = col.split()[0]
                        connection.execute(
                            text(f"ALTER TABLE settings ADD COLUMN {col_name} {col.split(' ', 1)[1]}")
                        )
                logger.info(f"Added missing settings columns: {missing_settings_cols}")

        # Check contacts for tags column (JSON in MySQL, JSON in PostgreSQL, TEXT fallback for SQLite)
        if "contacts" in table_names:
            columns = {column["name"] for column in inspector.get_columns("contacts")}
            if "tags" not in columns:
                with engine.begin() as connection:
                    # Use appropriate column type based on database backend
                    dialect_name = engine.dialect.name
                    if dialect_name == "mysql":
                        connection.execute(text("ALTER TABLE contacts ADD COLUMN tags JSON DEFAULT '[]'"))
                    elif dialect_name == "postgresql":
                        connection.execute(text("ALTER TABLE contacts ADD COLUMN tags JSONB DEFAULT '[]'"))
                    else:
                        connection.execute(text("ALTER TABLE contacts ADD COLUMN tags TEXT DEFAULT '[]'"))
                logger.info("Added missing contacts.tags column")

        # Brevo-style list folders and per-list campaign settings.
        if "contact_lists" in table_names:
            columns = {column["name"] for column in inspector.get_columns("contact_lists")}
            missing_list_cols = []
            if "folder_id" not in columns:
                missing_list_cols.append("folder_id INTEGER NULL")
            if "from_name" not in columns:
                missing_list_cols.append("from_name VARCHAR(255) NULL")
            if "from_email" not in columns:
                missing_list_cols.append("from_email VARCHAR(255) NULL")
            if "reply_to" not in columns:
                missing_list_cols.append("reply_to VARCHAR(255) NULL")
            if "header" not in columns:
                missing_list_cols.append("header TEXT NULL")
            if "footer" not in columns:
                missing_list_cols.append("footer TEXT NULL")
            if missing_list_cols:
                with engine.begin() as connection:
                    for col in missing_list_cols:
                        col_name, col_type = col.split(" ", 1)
                        connection.execute(
                            text(f"ALTER TABLE contact_lists ADD COLUMN {col_name} {col_type}")
                        )
                logger.info("Added missing contact_lists columns: %s", missing_list_cols)

        if "contact_list_members" in table_names:
            columns = {
                column["name"]
                for column in inspector.get_columns("contact_list_members")
            }
            if "unsubscribed" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE contact_list_members "
                            "ADD COLUMN unsubscribed BOOLEAN DEFAULT 0"
                        )
                    )
                logger.info("Added missing contact_list_members.unsubscribed column")

        if "contacts" in table_names:
            columns = {column["name"] for column in inspector.get_columns("contacts")}
            if "email_blacklisted" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE contacts "
                            "ADD COLUMN email_blacklisted BOOLEAN DEFAULT 0"
                        )
                    )
                logger.info("Added missing contacts.email_blacklisted column")

        # Campaigns are newer than most rows: link drafts back to the campaign
        # that produced them so per-campaign results need no extra table.
        if "drafts" in table_names:
            columns = {column["name"] for column in inspector.get_columns("drafts")}
            if "campaign_id" not in columns:
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE drafts ADD COLUMN campaign_id INTEGER NULL")
                    )
                logger.info("Added missing drafts.campaign_id column")

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