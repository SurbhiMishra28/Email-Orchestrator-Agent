"""A seeded demo workspace behind the public sign-in page.

The demo exists so a visitor can click through the product without an account.
It is a *real* tenant with its own rows: nothing a visitor does there can reach
the operator's workspace, and the same tenant is reused on every visit so the
seed is written once.

The demo never inherits the deployment environment, so it has no sending
credentials and cannot deliver mail.
"""
import logging
import secrets

from app.db import Campaign, Contact, SessionLocal, Settings, Template, Tenant, User
from app.auth import hash_password
from app.services.provisioning import provision_tenant_defaults

logger = logging.getLogger(__name__)

DEMO_SUBDOMAIN = "demo"
DEMO_EMAIL = "demo@mailmatrix.local"
DEMO_TENANT_NAME = "Demo workspace"

_CONTACTS = [
    ("ada@northwind.io", "Ada Lovelace", "Northwind", "Head of Growth", "interested"),
    ("grace@hopper.dev", "Grace Hopper", "Hopper Labs", "CTO", "replied"),
    ("alan@bletchley.co", "Alan Turing", "Bletchley", "Founder", "interested"),
    ("katherine@nasa.gov", "Katherine Johnson", "Orbital", "VP Sales", "not_interested"),
    ("linus@kernel.org", "Linus Pauling", "Kernel Co", "Engineer", ""),
    ("margaret@mit.edu", "Margaret Hamilton", "MIT", "Director", "replied"),
    ("dennis@bell-labs.com", "Dennis Ritchie", "Bell Labs", "Principal", ""),
    ("barbara@navy.mil", "Barbara Liskov", "Naval Systems", "Architect", "interested"),
]


def _seed(db, tenant_id: int) -> None:
    """Give the demo enough rows that every screen has something to show."""
    settings = db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
    if settings:
        settings.business_name = "Northwind Labs"
        settings.business_offer = "Outbound infrastructure for modern revenue teams."
        settings.goal = "Book 20 qualified demos this month."

    # Contact.email is globally unique, so the demo addresses are namespaced.
    for email, name, company, role, tag in _CONTACTS:
        exists = (
            db.query(Contact.id)
            .filter(Contact.email == email)
            .first()
        )
        if exists:
            continue
        db.add(
            Contact(
                tenant_id=tenant_id,
                email=email,
                name=name,
                company=company,
                role=role,
                eligible_to_email=True,
                tags=[tag] if tag else [],
            )
        )

    intro = Template(
        tenant_id=tenant_id,
        name="Intro — Northwind",
        category="intro",
        subject_template="{{ company }} + MailMatrix",
        body_template=(
            "Hi {{ first_name }},\n\n"
            "I saw {{ company }} is scaling outbound. We help teams like yours "
            "run every provider from one queue, with AI routing and reply "
            "handling built in.\n\n"
            "Worth a 15-minute look next week?"
        ),
        tags=["intro"],
        is_active=True,
    )
    followup = Template(
        tenant_id=tenant_id,
        name="Follow-up — day 3",
        category="followup",
        subject_template="Re: {{ company }} + MailMatrix",
        body_template=(
            "Hi {{ first_name }},\n\n"
            "Floating this back to the top of your inbox in case it got buried.\n\n"
            "Happy to send over the deliverability numbers if useful."
        ),
        tags=["followup"],
        is_active=True,
    )
    db.add_all([intro, followup])
    db.flush()

    if not db.query(Campaign).filter(Campaign.tenant_id == tenant_id).first():
        db.add(
            Campaign(
                tenant_id=tenant_id,
                name="Q3 — Northwind outbound",
                subject="{{ company }} + MailMatrix",
                status="draft",
                template_id=intro.id,
                campaign_type="marketing",
                timezone="UTC",
            )
        )


def ensure_demo_tenant(db) -> Tenant:
    """Return the demo tenant, creating and seeding it on first use."""
    tenant = db.query(Tenant).filter(Tenant.subdomain == DEMO_SUBDOMAIN).first()
    if tenant is not None:
        return tenant

    tenant = Tenant(
        name=DEMO_TENANT_NAME,
        subdomain=DEMO_SUBDOMAIN,
        plan="pro",
        daily_email_limit=1000,
    )
    db.add(tenant)
    db.flush()

    # No environment inheritance: the demo must never hold real credentials.
    provision_tenant_defaults(db, tenant.id, inherit_environment=False)
    _seed(db, tenant.id)
    db.commit()
    db.refresh(tenant)
    logger.info("Demo workspace provisioned (tenant %s)", tenant.id)
    return tenant


def ensure_demo_user(db, tenant: Tenant) -> User:
    """Return the demo account, creating it with an unusable password."""
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is not None:
        return user

    user = User(
        tenant_id=tenant.id,
        email=DEMO_EMAIL,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        name="Demo",
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user