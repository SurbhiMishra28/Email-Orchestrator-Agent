"""Per-tenant bootstrap data.

Registration, startup and any future tenant creation must produce the same
rows. Keeping the logic here avoids importing ``app.main`` from routers, which
would be circular.
"""
from app.config import settings as app_settings
from app.db import IMAPConfig, Settings, SMTPConfig, Template

# Bump this when the seeded wording changes. Templates carry the version they
# were seeded with, so an upgrade can refresh stock wording without touching a
# template the operator has edited.
DEFAULT_TEMPLATE_VERSION = 2

DEFAULT_INTRO_SUBJECT = "A quick introduction from Skora Infotech"
DEFAULT_INTRO_BODY = (
    "Hi {{ first_name or 'there' }},\n\n"
    "This is {{ sender_name or 'Surbhi Mishra' }} from {{ business_name or 'Skora Infotech' }}. "
    "We work with businesses to grow their online presence through websites, "
    "marketing and SEO.\n\n"
    "I noticed {{ company or 'your business' }} might be interested in growing "
    "its online presence. Would you be open to a quick chat about how we can help?\n\n"
    "If yes, I can share some ideas that might work for {{ company or 'you' }}.\n\n"
    "Best,\n"
    "{{ sender_name or 'Surbhi Mishra' }}\n"
    "{{ sender_role or 'Sales Manager' }}\n"
    "{{ business_name or 'Skora Infotech Pvt Ltd' }}\n"
    "{% if business_address %}{{ business_address }}\n{% endif %}"
    "{% if company_website %}{{ company_website }}{% endif %}"
)

# Seeded reply template. The auto-responder answers classified inbound replies;
# without a row in this category there is nothing for the UI to show and nothing
# for the reply agent to fall back to, so a fresh workspace answers with the
# hardcoded Python template instead of an editable one.
DEFAULT_REPLY_SUBJECT = "Re: {{ subject }}"
DEFAULT_REPLY_BODY = (
    "Hi {{ first_name or 'there' }},\n\n"
    "Thanks for getting back to me.\n\n"
    "{% if calendly_url %}You can grab a time that suits you here: "
    "{{ calendly_url }}{% else %}Let me know a couple of times that work for you "
    "and I'll send an invite.{% endif %}\n\n"
    "Best,\n"
    "{{ sender_name or 'Surbhi Mishra' }}\n"
    "{{ sender_role or 'Sales Manager' }}\n"
    "{{ business_name or 'Skora Infotech Pvt Ltd' }}\n"
    "{% if business_address %}{{ business_address }}\n{% endif %}"
    "{% if company_website %}{{ company_website }}{% endif %}"
)

# Seeded follow-up template. The day-3 and day-5 nudges reuse this body, so it
# has to stand on its own: it restates the value, answers the two objections
# that actually stall a cold thread (timing and relevance), and offers a
# low-friction exit. The earlier one-liner read as an accident.
DEFAULT_FOLLOWUP_SUBJECT = "Re: {{ subject }}"
DEFAULT_FOLLOWUP_BODY = (
    "Hi {{ first_name or 'there' }},\n\n"
    "Bringing this back to the top of your inbox in case my last note got buried.\n\n"
    "We help businesses like {{ company or 'yours' }} grow their online presence "
    "through websites, marketing and SEO. If that is on your list this quarter, I "
    "would be glad to share a few ideas that might work for you.\n\n"
    "Would you be open to a quick chat?\n"
    "{% if calendly_url %}{{ calendly_url }}{% else %}Reply with a day that suits "
    "you and I will send an invite.{% endif %}\n\n"
    "If the timing is wrong, just say so and I will close the loop and come back "
    "next quarter.\n\n"
    "Best,\n"
    "{{ sender_name or 'Surbhi Mishra' }}\n"
    "{{ sender_role or 'Sales Manager' }}\n"
    "{{ business_name or 'Skora Infotech Pvt Ltd' }}\n"
    "{% if business_address %}{{ business_address }}\n{% endif %}"
    "{% if company_website %}{{ company_website }}{% endif %}"
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
    the implicit workspace of this no-login app, where it *is* the mailbox
    owner, and wrong for every other tenant: on a public deployment the
    environment holds the operator's own SMTP password, so copying it would let
    anyone who registers send mail as that account. It defaults to on, and
    ``app.main`` passes it explicitly so only the implicit workspace inherits.
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

    # A sender alias matching the mailbox, so the alias list is never empty and
    # sending has a From identity to use. The address comes from the tenant's own
    # mailbox rather than the process environment, so a tenant that did not
    # inherit the operator's credentials gets no alias pointing at them.
    from app.db import EmailAlias

    has_alias = (
        db.query(EmailAlias).filter(EmailAlias.tenant_id == tenant_id).first()
    )
    if not has_alias:
        alias_email = (smtp_row.sender or smtp_row.user or "").strip()
        if alias_email:
            db.add(
                EmailAlias(
                    tenant_id=tenant_id,
                    name=app_settings.SENDER_NAME or "",
                    email=alias_email,
                    is_default=True,
                    is_active=True,
                )
            )

    imap_row = db.query(IMAPConfig).filter(IMAPConfig.tenant_id == tenant_id).first()
    if not imap_row:
        imap_row = IMAPConfig(tenant_id=tenant_id)
        db.add(imap_row)

    if inherit_environment:
        if not imap_row.host and app_settings.IMAP_HOST:
            imap_row.host = app_settings.IMAP_HOST
        if not imap_row.port or imap_row.port == 993:
            imap_row.port = app_settings.IMAP_PORT or imap_row.port
        if not imap_row.user and app_settings.IMAP_USER:
            imap_row.user = app_settings.IMAP_USER
        if not imap_row.password and app_settings.IMAP_PASSWORD:
            imap_row.password = app_settings.IMAP_PASSWORD

    imap_row.configured = bool(imap_row.host and imap_row.user and imap_row.password)

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
                    subject_template=DEFAULT_FOLLOWUP_SUBJECT,
                    body_template=DEFAULT_FOLLOWUP_BODY,
                ),
                Template(
                    tenant_id=tenant_id,
                    name="Reply",
                    category="reply",
                    subject_template=DEFAULT_REPLY_SUBJECT,
                    body_template=DEFAULT_REPLY_BODY,
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

        # Replace the old one-line follow-up with the fuller body. Only the
        # seeded stub is touched: an operator who has written their own follow-up
        # keeps it.
        legacy_followup = (
            db.query(Template)
            .filter(
                Template.tenant_id == tenant_id,
                Template.category == "followup",
            )
            .first()
        )
        if legacy_followup and "Just wanted to follow up" in (
            legacy_followup.body_template or ""
        ):
            legacy_followup.subject_template = DEFAULT_FOLLOWUP_SUBJECT
            legacy_followup.body_template = DEFAULT_FOLLOWUP_BODY

    # Backfill the reply template for workspaces created before it existed. The
    # auto-responder falls back to a hardcoded body when no active reply template
    # is present, so without this an upgraded workspace would keep answering with
    # wording the user cannot edit in the dashboard.
    has_reply = (
        db.query(Template)
        .filter(
            Template.tenant_id == tenant_id,
            Template.category == "reply",
            Template.is_active == True,  # noqa: E712 - SQLAlchemy boolean
        )
        .first()
    )
    if not has_reply:
        db.add(
            Template(
                tenant_id=tenant_id,
                name="Reply",
                category="reply",
                subject_template=DEFAULT_REPLY_SUBJECT,
                body_template=DEFAULT_REPLY_BODY,
            )
        )

    _upgrade_stock_templates(db, tenant_id)

    db.commit()


# Bodies this app has shipped as defaults. A template whose body is still one of
# these is stock, so an upgrade may refresh it; anything else is the operator's
# own writing and is left alone.
_STOCK_BODIES = {
    "intro": {
        "Hi {{ first_name or 'there' }},\n\nI'm reaching out from {{ business_name or 'our team' }}. {{ business_offer }}\n\nWould you be open to a short conversation to see if this is relevant?\n{% if calendly_url %}Choose a time: {{ calendly_url }}{% else %}If so, reply and we can coordinate a time.{% endif %}\n\n{{ sender_name or 'Best regards' }}",
        "Hi {{first_name}},\n\nJust wanted to follow up on my previous email...",
    },
    "followup": {
        "Hi {{first_name}},\n\nJust wanted to follow up on my previous email...",
        "Hi {{ first_name or 'there' }},\n\nI wanted to bring this back to the top of your inbox in case my last note landed at a busy moment.\n\nThe short version: {{ business_offer }} Most teams I speak with are not looking for a new vendor -- they are looking for one less thing to chase. That is usually the gap worth 15 minutes.\n\nIf the timing is wrong, just say so and I will close the loop and come back next quarter. If it is relevant, here is the easiest next step:\n{% if calendly_url %}{{ calendly_url }}{% else %}reply with a day that works and I will send an invite.{% endif %}\n\nEither way, thanks for reading this far.\n\n{{ sender_name or 'Best regards' }}",
    },
    "reply": {
        "Hi {{ first_name or 'there' }},\n\nThanks for getting back to me. {{ business_offer }}\n\n{% if calendly_url %}You can grab a time that suits you here: {{ calendly_url }}{% else %}Let me know a couple of times that work for you and I'll send an invite.{% endif %}\n\n{{ sender_name or 'Best regards' }}",
    },
}

_STOCK_SUBJECTS = {
    "intro": {"A quick introduction"},
    "followup": {"Following up"},
    "reply": {"Re: {{ subject }}"},
}

_NEW_DEFAULTS = {
    "intro": (DEFAULT_INTRO_SUBJECT, DEFAULT_INTRO_BODY),
    "followup": (DEFAULT_FOLLOWUP_SUBJECT, DEFAULT_FOLLOWUP_BODY),
    "reply": (DEFAULT_REPLY_SUBJECT, DEFAULT_REPLY_BODY),
}


def _upgrade_stock_templates(db, tenant_id: int) -> int:
    """Refresh seeded wording on an upgraded database.

    Only rows whose body still matches a shipped default are touched, so a
    template the operator edited in the dashboard is never overwritten.
    """
    upgraded = 0
    for category, (new_subject, new_body) in _NEW_DEFAULTS.items():
        rows = (
            db.query(Template)
            .filter(Template.tenant_id == tenant_id, Template.category == category)
            .all()
        )
        for row in rows:
            body = (row.body_template or "").strip()
            subject = (row.subject_template or "").strip()
            if body in _STOCK_BODIES.get(category, set()) or subject in _STOCK_SUBJECTS.get(
                category, set()
            ):
                row.subject_template = new_subject
                row.body_template = new_body
                upgraded += 1
    return upgraded
