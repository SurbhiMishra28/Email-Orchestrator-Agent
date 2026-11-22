"""A shared, read-only demo workspace.

A visitor who has no account can press "Explore the demo" on the sign-in screen
and land in a workspace that already looks lived in: lists, contacts, templates,
campaigns, sent drafts, replies and verification results.

Two rules make this safe to expose on a public deployment:

1. The workspace is one fixed tenant identified by ``subdomain="demo"``, so
   every visitor sees the same data and no visitor creates a tenant of their own.
2. Sending is refused for that tenant (see ``ensure_sending_allowed`` in
   ``app.deps``). Seeded recipients use reserved ``.example.com`` addresses,
   which the placeholder guard already rejects, but the demo must also never
   touch a real relay even if a visitor edits the contacts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.db import (
    ABTest,
    ABVariant,
    Campaign,
    Contact,
    ContactList,
    ContactListFolder,
    ContactListMember,
    Draft,
    EmailVerification,
    Event,
    InboxMessage,
    Log,
    SessionLocal,
    Settings,
    SMTPConfig,
    Tenant,
    TenantMember,
    Template,
    UsageLog,
    User,
)
from app.services.usage import EMAILS_SENT

logger = logging.getLogger(__name__)

DEMO_SUBDOMAIN = "demo"
DEMO_EMAIL = "demo@mailmatrix.app"
DEMO_PASSWORD = "DemoAccess2026!"
DEMO_USER_NAME = "Demo Operator"
DEMO_TENANT_NAME = "MailMatrix Demo"

# Every seeded recipient is reserved-domain, so the placeholder guard refuses to
# mail them even if the sending guard is ever bypassed by a future code path.
DEMO_DOMAIN = "example.com"

DEMO_CONTACTS = [
    ("Maya Chen", "maya.chen", "Northwind Analytics", "VP of Sales", "SaaS"),
    ("Tobias Grant", "tobias.grant", "Kestrel Labs", "Head of Growth", "Developer tools"),
    ("Priya Raman", "priya.raman", "Lumen Health", "Director of Ops", "Healthcare"),
    ("Daniel Okafor", "daniel.okafor", "Bramble Logistics", "COO", "Logistics"),
    ("Sofia Almeida", "sofia.almeida", "Ardent Financial", "VP Marketing", "Fintech"),
    ("Jonas Weber", "jonas.weber", "Halden Manufacturing", "Plant Director", "Manufacturing"),
    ("Amara Nwosu", "amara.nwosu", "Cobalt Studio", "Founder", "Design"),
    ("Ethan Brooks", "ethan.brooks", "Ridgeline Security", "CISO", "Security"),
    ("Lucia Ferrari", "lucia.ferrari", "Verdant Foods", "Head of Retail", "Consumer"),
    ("Ravi Patel", "ravi.patel", "Summit Learning", "VP Product", "Edtech"),
    ("Nora Lindqvist", "nora.lindqvist", "Fjord Mobility", "GM", "Mobility"),
    ("Caleb Ortiz", "caleb.ortiz", "Pinegate Property", "Head of Leasing", "Real estate"),
    ("Hannah Kim", "hannah.kim", "Beacon Insurance", "VP Partnerships", "Insurance"),
    ("Omar Haddad", "omar.haddad", "Atlas Freight", "Head of Revenue", "Logistics"),
    ("Ingrid Solberg", "ingrid.solberg", "Nordvik Energy", "Director of Sales", "Energy"),
    ("Felix Moreau", "felix.moreau", "Maison Clair", "Managing Director", "Hospitality"),
    ("Ayesha Siddiqui", "ayesha.siddiqui", "Orbit Commerce", "Head of CRM", "Retail"),
    ("Gustav Bauer", "gustav.bauer", "Steinbach Robotics", "VP Engineering", "Industrial"),
]

DEMO_FOLDERS = ["Q4 outbound", "Partnerships", "Re-engagement"]

DEMO_LISTS = [
    ("SaaS leaders", "Q4 outbound", "VPs and heads of sales at mid-market SaaS companies"),
    ("Logistics operators", "Q4 outbound", "Ops and revenue leaders in freight and logistics"),
    ("Fintech execs", "Partnerships", "Marketing and partnerships leads in fintech"),
    ("Lapsed trials", "Re-engagement", "Signed up, never sent a campaign"),
]

DEMO_TEMPLATES = [
    (
        "Intro — problem first",
        "intro",
        "A quick idea for {{company}}",
        "Hi {{ first_name or 'there' }},\n\n"
        "Most {{industry}} teams I speak with are still running outbound from a "
        "spreadsheet. {{business_offer}}\n\n"
        "Open to a 15-minute call this week?\n\n{{ sender_name or 'Best regards' }}",
    ),
    (
        "Intro — social proof",
        "intro",
        "{{company}} + {{business_name}}",
        "Hi {{ first_name or 'there' }},\n\n"
        "We helped three {{industry}} teams cut manual follow-up by half last "
        "quarter. {{business_offer}}\n\n"
        "Worth a short conversation?\n\n{{ sender_name or 'Best regards' }}",
    ),
    (
        "Follow-up — day 3",
        "followup",
        "Re: A quick idea for {{company}}",
        "Hi {{ first_name or 'there' }},\n\n"
        "Floating this back up in case it got buried. Happy to send a two-minute "
        "walkthrough instead of a call.\n\n{{ sender_name or 'Best regards' }}",
    ),
    (
        "Reply — booking a call",
        "reply",
        "Re: {{company}}",
        "Hi {{ first_name or 'there' }},\n\n"
        "Great to hear from you. Here are two slots that usually work: "
        "Tuesday 10:00 and Thursday 14:00.\n\n{{ sender_name or 'Best regards' }}",
    ),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def demo_tenant_id(db) -> Optional[int]:
    """Return the demo tenant's id, or None when it has not been seeded yet."""
    row = (
        db.query(Tenant.id)
        .filter(Tenant.subdomain == DEMO_SUBDOMAIN)
        .first()
    )
    return row[0] if row else None


def is_demo_tenant(db, tenant_id: Optional[int]) -> bool:
    """True when ``tenant_id`` is the shared demo workspace."""
    if tenant_id is None:
        return False
    return (
        db.query(Tenant.id)
        .filter(Tenant.id == tenant_id, Tenant.subdomain == DEMO_SUBDOMAIN)
        .first()
        is not None
    )


def _get_or_create_tenant(db) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.subdomain == DEMO_SUBDOMAIN).first()
    if tenant is not None:
        return tenant

    tenant = Tenant(
        name=DEMO_TENANT_NAME,
        subdomain=DEMO_SUBDOMAIN,
        plan="pro",
        daily_email_limit=50,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _get_or_create_user(db, tenant: Tenant) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is not None:
        # Keep the demo password current after a rotation of the constant.
        if not user.is_active:
            user.is_active = True
        return user

    user = User(
        tenant_id=tenant.id,
        email=DEMO_EMAIL,
        hashed_password=hash_password(DEMO_PASSWORD),
        name=DEMO_USER_NAME,
        role="admin",
    )
    db.add(user)
    db.flush()
    db.add(
        TenantMember(
            user_id=user.id,
            tenant_id=tenant.id,
            role="admin",
            accepted_at=_utcnow(),
        )
    )
    return user


def _seed_settings(db, tenant: Tenant) -> None:
    row = db.query(Settings).filter(Settings.tenant_id == tenant.id).first()
    if row is None:
        row = Settings(tenant_id=tenant.id)
        db.add(row)
    row.goal = "book intro calls with sales leaders"
    row.business_name = "MailMatrix"
    row.business_offer = (
        "MailMatrix drafts, paces and follows up on outbound so a two-person "
        "team can run a pipeline that looks like a ten-person one."
    )
    row.daily_cap = 50
    row.domain_cap = 3
    # Autopilot stays off. Enabling it is a per-tenant action the demo can take,
    # but a shared workspace should never start sending on a timer: the visitor
    # who turned it on is gone, and the next visitor inherits a running queue.
    row.AUTOPILOT = False
    row.AUTO_APPROVE = False
    row.footer_text = "You are receiving this because we met at a conference."
    row.sender_name = "Priya from MailMatrix"
    row.sender_role = "Head of Growth"
    row.company_website = "https://mailmatrix.example.com"
    row.calendly_url = "https://cal.example.com/priya/15min"
    row.tracking_enabled = True

    smtp = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == tenant.id).first()
    if smtp is None:
        smtp = SMTPConfig(tenant_id=tenant.id)
        db.add(smtp)
        # Blank on creation, never inherited from the environment: the demo is
        # public, so the deployment's own mailbox must not be reachable from it.
        # A visitor who wants to try a real send configures their own relay.
        smtp.host = ""
        smtp.port = 587
        smtp.user = ""
        smtp.password = ""
        smtp.sender = ""
        smtp.configured = False
        smtp.authentication_configured = False
    # An existing row is left alone: re-seeding at startup must not wipe the
    # relay a visitor saved while trying the sending flow.


def _seed_templates(db, tenant: Tenant) -> list:
    created = []
    for name, category, subject, body in DEMO_TEMPLATES:
        row = (
            db.query(Template)
            .filter(Template.tenant_id == tenant.id, Template.name == name)
            .first()
        )
        if row is None:
            row = Template(
                tenant_id=tenant.id,
                name=name,
                category=category,
                subject_template=subject,
                body_template=body,
            )
            db.add(row)
            db.flush()
        created.append(row)
    return created


def _seed_contacts(db, tenant: Tenant) -> list:
    folder_ids = {}
    for name in DEMO_FOLDERS:
        folder = (
            db.query(ContactListFolder)
            .filter(
                ContactListFolder.tenant_id == tenant.id,
                ContactListFolder.name == name,
            )
            .first()
        )
        if folder is None:
            folder = ContactListFolder(tenant_id=tenant.id, name=name)
            db.add(folder)
            db.flush()
        folder_ids[name] = folder.id

    list_rows = {}
    for name, folder_name, description in DEMO_LISTS:
        row = (
            db.query(ContactList)
            .filter(ContactList.tenant_id == tenant.id, ContactList.name == name)
            .first()
        )
        if row is None:
            row = ContactList(
                tenant_id=tenant.id,
                folder_id=folder_ids.get(folder_name),
                name=name,
                description=description,
                from_name="Priya from MailMatrix",
                from_email=f"priya@{DEMO_DOMAIN}",
            )
            db.add(row)
            db.flush()
        list_rows[name] = row

    contacts = []
    for index, (name, handle, company, role, industry) in enumerate(DEMO_CONTACTS):
        email = f"{handle}@{DEMO_DOMAIN}"
        row = db.query(Contact).filter(Contact.email == email).first()
        if row is None:
            row = Contact(
                tenant_id=tenant.id,
                email=email,
                name=name,
                company=company,
                role=role,
                industry=industry,
                # Marked eligible so the UI shows real eligibility states; the
                # reserved domain is what stops an actual send.
                eligible_to_email=index % 7 != 6,
                email_blacklisted=False,
                tags=["demo", industry.lower()],
            )
            db.add(row)
            db.flush()
        contacts.append(row)

        list_name = [
            "SaaS leaders",
            "Logistics operators",
            "Fintech execs",
            "Lapsed trials",
        ][index % 4]
        membership = (
            db.query(ContactListMember)
            .filter(
                ContactListMember.list_id == list_rows[list_name].id,
                ContactListMember.contact_id == row.id,
            )
            .first()
        )
        if membership is None:
            db.add(
                ContactListMember(
                    tenant_id=tenant.id,
                    list_id=list_rows[list_name].id,
                    contact_id=row.id,
                )
            )
    return contacts


def _seed_campaigns(db, tenant: Tenant, templates: list, lists: list) -> None:
    plans = [
        ("Q4 SaaS outbound", "sent", "A quick idea for {{company}}", 0, 0),
        ("Logistics partnerships", "sending", "{{company}} + MailMatrix", 1, 1),
        ("Lapsed trial winback", "draft", "Still exploring outbound?", 0, 3),
    ]
    for name, status, subject, template_index, list_index in plans:
        exists = (
            db.query(Campaign)
            .filter(Campaign.tenant_id == tenant.id, Campaign.name == name)
            .first()
        )
        if exists:
            continue
        template = templates[template_index % len(templates)]
        contact_list = lists[list_index % len(lists)]
        sent_at = _utcnow() - timedelta(days=6) if status == "sent" else None
        db.add(
            Campaign(
                tenant_id=tenant.id,
                name=name,
                subject=subject,
                channel="email",
                status=status,
                template_id=template.id,
                list_id=contact_list.id,
                total_recipients=6,
                delivered=6 if status == "sent" else 2,
                opened=4 if status == "sent" else 1,
                clicked=2 if status == "sent" else 0,
                replied=2 if status == "sent" else 0,
                bounced=0,
                unsubscribed=1 if status == "sent" else 0,
                sent_at=sent_at,
            )
        )


def _seed_drafts(db, tenant: Tenant, contacts: list, templates: list) -> None:
    if db.query(Draft).filter(Draft.tenant_id == tenant.id).first():
        return

    now = _utcnow()
    sent_plan = [0, 1, 2, 3, 4, 5, 6]
    for offset, index in enumerate(sent_plan):
        contact = contacts[index]
        template = templates[index % len(templates)]
        db.add(
            Draft(
                tenant_id=tenant.id,
                contact_id=contact.id,
                subject=template.subject_template.replace(
                    "{{company}}", contact.company or "your team"
                ),
                body=(
                    f"Hi {(contact.name or 'there').split()[0]},\n\n"
                    "Most teams in your space are still running outbound from a "
                    "spreadsheet. MailMatrix drafts, paces and follows up so the "
                    "pipeline keeps moving without a tooling project.\n\n"
                    "Open to a 15-minute call this week?\n\nPriya"
                ),
                status="sent",
                created_at=now - timedelta(days=12 - offset, hours=3),
                sent_at=now - timedelta(days=12 - offset, hours=2),
                variables={"template_id": template.id, "agent": "PersonalizedEmailAgent"},
                attempt_count=1,
            )
        )

    for index, status in ((7, "draft"), (8, "draft"), (9, "draft"), (10, "failed")):
        contact = contacts[index]
        db.add(
            Draft(
                tenant_id=tenant.id,
                contact_id=contact.id,
                subject=f"Following up with {contact.company}",
                body=(
                    f"Hi {(contact.name or 'there').split()[0]},\n\n"
                    "Floating this back up in case it got buried.\n\nPriya"
                ),
                status=status,
                created_at=now - timedelta(days=2, hours=index),
                variables={"followup_for": index},
                attempt_count=1 if status == "failed" else 0,
                error_message=(
                    "SMTP not configured in this demo workspace" if status == "failed" else None
                ),
            )
        )


def _seed_events(db, tenant: Tenant, contacts: list) -> None:
    if db.query(Event).filter(Event.tenant_id == tenant.id).first():
        return

    now = _utcnow()
    replies = [
        (0, "positive_response", "Interested, asked for times next week", 3),
        (2, "schedule_call", "Asked to book Thursday afternoon", 4),
        (4, "question", "Asked how pricing works for 3 seats", 5),
        (6, "positive_response", "Wants a two-minute walkthrough", 7),
        (8, "question", "Asked whether it integrates with HubSpot", 8),
        (10, "negative_response", "Not the right time this quarter", 9),
        (12, "unsubscribe", "Asked to be removed", 10),
    ]
    for contact_index, reply_type, summary, days_ago in replies:
        contact = contacts[contact_index]
        db.add(
            Event(
                tenant_id=tenant.id,
                contact_id=contact.id,
                event_type="reply_received",
                data={
                    "classification": {
                        "reply_type": reply_type,
                        "summary": summary,
                        "confidence": 0.91,
                    },
                    "subject": f"Re: A quick idea for {contact.company}",
                },
                timestamp=now - timedelta(days=days_ago, hours=2),
            )
        )

    for offset in range(21):
        db.add(
            Event(
                tenant_id=tenant.id,
                contact_id=contacts[offset % len(contacts)].id,
                event_type="email_opened" if offset % 3 else "link_clicked",
                data={"demo": True},
                timestamp=now - timedelta(days=13 - (offset % 13), hours=offset % 12),
            )
        )

    for offset, days_ago in ((0, 3), (1, 4)):
        db.add(
            Event(
                tenant_id=tenant.id,
                contact_id=contacts[offset].id,
                event_type="auto_reply_sent",
                data={"classification": {"reply_type": "positive_response"}},
                timestamp=now - timedelta(days=days_ago, hours=1),
            )
        )


def _seed_logs(db, tenant: Tenant) -> None:
    if db.query(Log).filter(Log.tenant_id == tenant.id).first():
        return

    now = _utcnow()
    messages = [
        ("Autopilot disabled (auto-approve off)", "info", 0),
        ("Settings updated", "info", 0),
        ("Queued 7 intro drafts for the Q4 outbound list", "info", 1),
        ("Autopilot pass run manually: 3 intros drafted, 2 replies answered", "info", 2),
        ("SMTP test failed: demo workspace cannot send mail", "warning", 3),
        ("Inbox sync imported 4 new replies", "info", 4),
        ("Queued follow-up drafts for 2 contacts", "info", 5),
        ("Email verification job completed: 18 checked", "info", 6),
    ]
    for message, level, days_ago in messages:
        db.add(
            Log(
                tenant_id=tenant.id,
                message=message,
                level=level,
                timestamp=now - timedelta(days=days_ago, hours=5),
            )
        )


def _seed_inbox(db, tenant: Tenant) -> None:
    if db.query(InboxMessage).filter(InboxMessage.tenant_id == tenant.id).first():
        return

    now = _utcnow()
    rows = [
        (
            "maya.chen@" + DEMO_DOMAIN,
            "Re: A quick idea for Northwind Analytics",
            "Happy to chat. Next Tuesday or Thursday works on my side — send an invite.",
            1,
        ),
        (
            "priya.raman@" + DEMO_DOMAIN,
            "Re: Lumen Health + MailMatrix",
            "Can you share how the pacing works with multiple senders?",
            2,
        ),
        (
            "sofia.almeida@" + DEMO_DOMAIN,
            "Re: Ardent Financial",
            "Sounds relevant. What does pricing look like for a 5-person team?",
            3,
        ),
        (
            "ethan.brooks@" + DEMO_DOMAIN,
            "Re: Ridgeline Security",
            "Not this quarter, but ping me in January.",
            4,
        ),
    ]
    for index, (sender, subject, snippet, days_ago) in enumerate(rows):
        db.add(
            InboxMessage(
                tenant_id=tenant.id,
                uid=f"demo-{index + 1}",
                sender=sender,
                subject=subject,
                snippet=snippet,
                received_at=now - timedelta(days=days_ago, hours=index),
                processed=True,
                processed_at=now - timedelta(days=days_ago),
            )
        )


def _seed_verifications(db, tenant: Tenant, contacts: list) -> None:
    if db.query(EmailVerification).filter(EmailVerification.tenant_id == tenant.id).first():
        return

    now = _utcnow()
    statuses = ["deliverable"] * 12 + ["risky", "risky", "undeliverable", "inconclusive"]
    for index, status in enumerate(statuses):
        contact = contacts[index % len(contacts)]
        db.add(
            EmailVerification(
                tenant_id=tenant.id,
                email=contact.email,
                contact_id=contact.id,
                status=status,
                smtp_check="valid" if status == "deliverable" else "not_checked",
                mx_check="valid",
                catch_all=status == "risky",
                disposable=False,
                domain=DEMO_DOMAIN,
                last_checked=now - timedelta(days=index % 5, hours=index),
            )
        )


def _seed_ab_test(db, tenant: Tenant, templates: list) -> None:
    if db.query(ABTest).filter(ABTest.tenant_id == tenant.id).first():
        return

    template = templates[0]
    test = ABTest(
        tenant_id=tenant.id,
        name="Subject line: idea vs social proof",
        status="active",
        template_id=template.id,
    )
    db.add(test)
    db.flush()
    db.add_all(
        [
            ABVariant(
                tenant_id=tenant.id,
                ab_test_id=test.id,
                label="A",
                subject="A quick idea for {{company}}",
                body=template.body_template,
                weight=1,
            ),
            ABVariant(
                tenant_id=tenant.id,
                ab_test_id=test.id,
                label="B",
                subject="{{company}} + MailMatrix",
                body=template.body_template,
                weight=1,
            ),
        ]
    )


def _seed_usage(db, tenant: Tenant) -> None:
    if db.query(UsageLog).filter(UsageLog.tenant_id == tenant.id).first():
        return

    now = _utcnow()
    db.add(UsageLog(tenant_id=tenant.id, metric=EMAILS_SENT, quantity=7))
    for offset in range(1, 13):
        db.add(
            UsageLog(
                tenant_id=tenant.id,
                metric=EMAILS_SENT,
                quantity=2 + (offset % 4),
                created_at=now - timedelta(days=offset),
            )
        )


def seed_demo_workspace() -> Tuple[User, Tenant]:
    """Create (once) and return the shared demo account and its tenant.

    Idempotent: a second call reuses the rows and only fills in anything a
    previous partial run missed. Returns a detached-safe pair of ORM rows whose
    ids are read before the session closes.
    """
    db = SessionLocal()
    try:
        try:
            tenant = _get_or_create_tenant(db)
            user = _get_or_create_user(db, tenant)
            db.commit()
        except IntegrityError:
            # Two visitors pressed the button at once and lost the race on the
            # unique subdomain; the winner's rows are what we want.
            db.rollback()
            tenant = db.query(Tenant).filter(Tenant.subdomain == DEMO_SUBDOMAIN).one()
            user = db.query(User).filter(User.email == DEMO_EMAIL).one()

        _seed_settings(db, tenant)
        templates = _seed_templates(db, tenant)
        contacts = _seed_contacts(db, tenant)
        lists = (
            db.query(ContactList)
            .filter(ContactList.tenant_id == tenant.id)
            .order_by(ContactList.id.asc())
            .all()
        )
        _seed_campaigns(db, tenant, templates, lists)
        _seed_drafts(db, tenant, contacts, templates)
        _seed_events(db, tenant, contacts)
        _seed_logs(db, tenant)
        _seed_inbox(db, tenant)
        _seed_verifications(db, tenant, contacts)
        _seed_ab_test(db, tenant, templates)
        _seed_usage(db, tenant)
        db.commit()

        db.refresh(user)
        db.refresh(tenant)
        logger.info("Demo workspace ready (tenant %s)", tenant.id)
        return user, tenant
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
