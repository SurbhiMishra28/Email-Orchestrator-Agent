"""Per-tenant bootstrap data.

Registration, startup and any future tenant creation must produce the same
rows. Keeping the logic here avoids importing ``app.main`` from routers, which
would be circular.
"""
from app.config import settings as app_settings
from app.db import Settings, SMTPConfig, Template

DEFAULT_INTRO_SUBJECT = "A quick introduction"
DEFAULT_INTRO_BODY = (
    "Hi {{ first_name or 'there' }},\n\n"
    "I'm reaching out from {{ business_name or 'our team' }}. {{ business_offer }}\n\n"
    "Would you be open to a short conversation to see if this is relevant?\n"
    "{% if calendly_url %}Choose a time: {{ calendly_url }}{% else %}"
    "If so, reply and we can coordinate a time.{% endif %}\n\n"
    "{{ sender_name or 'Best regards' }}"
)

# Legacy category spellings (init_templates.py) mapped to the canonical ones the
# pipeline looks up. Without this, a deployment seeded by that script has
# templates that no send path ever matches.
LEGACY_CATEGORIES = {
    "personalized_mail": "intro",
    "followups_mail": "followup",
    "reply_mail": "reply",
}

# Categories that mean "first email to a new contact". Templates seeded by the
# legacy init script are migrated to "intro", but older rows may still carry a
# legacy name, so the send paths accept every known spelling.
INTRO_CATEGORIES = ("intro", "personalized_mail", "outreach", "initial")
FOLLOWUP_CATEGORIES = ("followup", "followups_mail")


def normalize_template_categories(db, tenant_id: int) -> int:
    """Rewrite legacy template categories to their canonical names.

    Idempotent, so it is safe on every startup.
    """
    changed = 0
    for legacy, canonical in LEGACY_CATEGORIES.items():
        changed += (
            db.query(Template)
            .filter(
                Template.tenant_id == tenant_id,
                Template.category == legacy,
            )
            .update({Template.category: canonical}, synchronize_session=False)
        )
    if changed:
        db.commit()
    return changed


def provision_tenant_defaults(db, tenant_id: int, inherit_environment: bool = None) -> None:
    """Create the per-tenant rows a new account needs.

    Idempotent: safe to call on every startup so tenants created before
    settings/SMTP/templates became per-tenant are filled in.

    ``inherit_environment`` controls whether the process environment (the
    deployment's ``.env``) is copied into this tenant's rows. That is right for
    the single-user local tool, where the one implicit tenant *is* the mailbox
    owner, and wrong for every other tenant: on a public deployment the
    environment holds the operator's own SMTP password, so copying it would let
    anyone who registers send mail as that account. It defaults to
    ``SINGLE_USER_MODE``, which is itself forced off on a hosted platform.
    """
    if inherit_environment is None:
        inherit_environment = app_settings.SINGLE_USER_MODE

    if not db.query(Settings).filter(Settings.tenant_id == tenant_id).first():
        db.add(
            Settings(
                tenant_id=tenant_id,
                goal=app_settings.DEFAULT_GOAL,
                business_name=app_settings.DEFAULT_BUSINESS_NAME,
                business_offer=app_settings.DEFAULT_BUSINESS_OFFER,
                # A brand-new tenant never starts sending unattended, no matter
                # what the deployment's own environment asks for.
                AUTOPILOT=app_settings.DEFAULT_AUTOPILOT and inherit_environment,
                AUTO_APPROVE=app_settings.DEFAULT_AUTO_APPROVE and inherit_environment,
            )
        )

    smtp_row = db.query(SMTPConfig).filter(SMTPConfig.tenant_id == tenant_id).first()
    if not smtp_row:
        smtp_row = SMTPConfig(tenant_id=tenant_id)
        db.add(smtp_row)

    if inherit_environment:
        if not smtp_row.host and app_settings.DEFAULT_SMTP_HOST:
            smtp_row.host = app_settings.DEFAULT_SMTP_HOST
        if app_settings.DEFAULT_SMTP_PORT:
            smtp_row.port = app_settings.DEFAULT_SMTP_PORT
        if not smtp_row.user and app_settings.DEFAULT_SMTP_USER:
            smtp_row.user = app_settings.DEFAULT_SMTP_USER
        if not smtp_row.password and app_settings.DEFAULT_SMTP_PASSWORD:
            smtp_row.password = app_settings.DEFAULT_SMTP_PASSWORD
        if not smtp_row.sender and app_settings.DEFAULT_SMTP_SENDER:
            smtp_row.sender = app_settings.DEFAULT_SMTP_SENDER

    smtp_row.configured = bool(smtp_row.host and (smtp_row.sender or smtp_row.user))
    smtp_row.authentication_configured = bool(smtp_row.user and smtp_row.password)

    # Existing rows may use a legacy category; migrate them before the count
    # check below decides whether this tenant still needs default templates.
    normalize_template_categories(db, tenant_id)

    if db.query(Template).filter(Template.tenant_id == tenant_id).count() == 0:
        db.add_all(
            [
                Template(
                    tenant_id=tenant_id,
                    name="Intro Email",
                    category="intro",
                    subject_template=DEFAULT_INTRO_SUBJECT,
                    body_template=DEFAULT_INTRO_BODY,
                ),
                Template(
                    tenant_id=tenant_id,
                    name="Follow-up",
                    category="followup",
                    subject_template="Following up",
                    body_template=(
                        "Hi {{first_name}},\n\nJust wanted to follow up on my "
                        "previous email..."
                    ),
                ),
            ]
        )
    else:
        legacy_intro = (
            db.query(Template)
            .filter(
                Template.tenant_id == tenant_id,
                Template.name == "Intro Email",
                Template.category == "intro",
            )
            .first()
        )
        if legacy_intro and "[solution]" in (legacy_intro.body_template or ""):
            legacy_intro.subject_template = DEFAULT_INTRO_SUBJECT
            legacy_intro.body_template = DEFAULT_INTRO_BODY

    db.commit()
