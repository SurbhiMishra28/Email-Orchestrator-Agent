"""Pydantic schemas for API request/response models."""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class ContactBase(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=255)
    company: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = Field(default=None, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=100)
    linkedin: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None
    eligible_to_email: bool = False
    email_blacklisted: bool = False
    tags: List[str] = []


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    industry: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None
    eligible_to_email: Optional[bool] = None
    email_blacklisted: Optional[bool] = None
    tags: Optional[List[str]] = None


class ContactOut(ContactBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class DraftBase(BaseModel):
    contact_id: int
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=50000)


class DraftCreate(DraftBase):
    # Optional sender override. When set, the queued draft is sent from this
    # identity instead of the tenant's default alias.
    alias_id: Optional[int] = None
    aliasId: Optional[int] = None
    from_email: Optional[str] = Field(default=None, max_length=255)
    from_name: Optional[str] = Field(default=None, max_length=255)


class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


class DraftOut(BaseModel):
    id: int
    contact_id: int
    subject: str
    body: str
    status: str
    variables: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class TemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(default="intro", max_length=100)
    subject_template: str = Field(..., min_length=1, max_length=500)
    body_template: str = Field(..., min_length=1, max_length=50000)
    footer_template: str = Field(default="", description="Footer to append to email body")
    variables: Dict[str, Any] = {}
    tags: List[str] = []
    is_active: bool = True


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    footer_template: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class TemplateOut(TemplateBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class TemplateUseRequest(BaseModel):
    template_id: int
    contact_id: int
    custom_values: Dict[str, Any] = {}
    auto_approve: bool = True
    send_via_smtp: bool = True


class TemplateExpandRequest(BaseModel):
    template_id: int
    contact_id: int
    custom_values: Dict[str, Any] = {}


class SMTPConfigBase(BaseModel):
    host: Optional[str] = None
    port: int = 587
    user: Optional[str] = None
    password: Optional[str] = None
    sender: Optional[str] = None


class SMTPConfigOut(SMTPConfigBase):
    configured: bool
    authentication_configured: bool = False
    # ``database`` when the tenant saved its own mailbox, ``environment`` when
    # the local single-user deployment supplied it.
    source: str = "database"
    transport: str = "smtp"

    model_config = ConfigDict(from_attributes=True)


class IMAPConfigBase(BaseModel):
    host: Optional[str] = None
    port: int = 993
    user: Optional[str] = None
    password: Optional[str] = None
    folder: str = "INBOX"


class IMAPConfigOut(BaseModel):
    host: Optional[str] = None
    port: int = 993
    user: Optional[str] = None
    folder: str = "INBOX"
    configured: bool = False
    source: str = "database"
    transport: str = "imap"

    model_config = ConfigDict(from_attributes=True)


class SettingsBase(BaseModel):
    goal: str = "book intro calls with sales leaders"
    business_name: str = ""
    business_offer: str = ""
    daily_cap: int = 50
    domain_cap: int = 3
    AUTO_APPROVE: bool = False
    AUTOPILOT: bool = False
    # Footer and sender signature configuration
    footer_text: str = ""
    sender_name: str = ""
    sender_role: str = ""
    company_website: str = ""
    calendly_url: str = ""
    # Opt-in open/click tracking. Off means outbound mail stays plain text.
    tracking_enabled: bool = False


class SettingsUpdate(SettingsBase):
    pass


class SettingsOut(SettingsBase):
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class EmailVerificationBase(BaseModel):
    email: EmailStr
    contact_id: Optional[int] = None
    status: str = Field(default="not_checked", pattern=r"^(not_checked|deliverable|undeliverable|risky|inconclusive)$")
    smtp_check: str = "not_checked"
    mx_check: str = "not_checked"
    catch_all: bool = False
    disposable: bool = False
    domain: Optional[str] = None


class EmailVerificationCreate(EmailVerificationBase):
    pass


class EmailVerificationOut(EmailVerificationBase):
    id: int
    last_checked: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class StateResponse(BaseModel):
    contacts: List[ContactOut] = []
    drafts: List[DraftOut] = []
    events: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []
    tools: List[Dict[str, Any]] = []
    analytics: Dict[str, Any] = {}
    settings: Optional[SettingsOut] = None
    smtp: Optional[SMTPConfigOut] = None


class HealthCheck(BaseModel):
    checks: Dict[str, Dict[str, Any]] = {}


class QueueStatus(BaseModel):
    alive: bool
    last_poll: Optional[float] = None
    pending_drafts: int = 0


# CSV Import batch
class CSVImport(BaseModel):
    csv: str
    # A list without an email_permission column would otherwise import every
    # row as ineligible, so nothing is ever sent. The uploader owns the list,
    # so rows are eligible unless they say otherwise; pass false to import
    # them paused for a manual review.
    default_eligible: bool = True