"""Seeded templates carry the signature block: name, title, company, address, site.

The address and the website are what make a cold email traceable to a real
company, so every seeded body must include both placeholders.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Settings, Template, Tenant
from app.services import provisioning
from app.services.provisioning import (
    DEFAULT_FOLLOWUP_BODY,
    DEFAULT_INTRO_BODY,
    DEFAULT_REPLY_BODY,
)


def _render(body, **extra):
    from jinja2 import Template as JinjaTemplate

    values = {
        "first_name": "Rajat",
        "company": "Acme",
        "sender_name": "Surbhi Mishra",
        "sender_title": "Sales Manager",
        "business_name": "Skora Infotech Pvt Ltd",
        "business_address": "Tower B, Noida, UP 201301",
        "company_website": "https://skorainfotech.com",
        "calendly_url": "",
        "subject": "Introduction",
        "business_offer": "websites and SEO",
    }
    values.update(extra)
    return JinjaTemplate(body).render(**values)


def test_intro_has_signature_address_and_site():
    out = _render(DEFAULT_INTRO_BODY)
    assert "Surbhi Mishra" in out
    assert "Sales Manager" in out
    assert "Skora Infotech Pvt Ltd" in out
    assert "Tower B, Noida, UP 201301" in out
    assert "https://skorainfotech.com" in out
    assert "Rajat" in out


def test_followup_has_signature_address_and_site():
    out = _render(DEFAULT_FOLLOWUP_BODY)
    assert "Surbhi Mishra" in out
    assert "Tower B, Noida, UP 201301" in out
    assert "https://skorainfotech.com" in out


def test_reply_has_signature_address_and_site():
    out = _render(DEFAULT_REPLY_BODY)
    assert "Surbhi Mishra" in out
    assert "Tower B, Noida, UP 201301" in out
    assert "https://skorainfotech.com" in out


def test_address_and_site_are_optional():
    """A tenant without them must not render empty lines."""
    out = _render(DEFAULT_INTRO_BODY, business_address="", company_website="")
    assert "None" not in out


def test_provisioning_seeds_all_three_categories():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    db.add(Tenant(id=1, name="T"))
    db.add(Settings(tenant_id=1, business_name="Skora Infotech Pvt Ltd"))
    db.commit()

    provisioning.provision_tenant_defaults(db, tenant_id=1, inherit_environment=False)

    rows = db.query(Template).filter(Template.tenant_id == 1).all()
    assert {r.category for r in rows} == {"intro", "followup", "reply"}
    for r in rows:
        assert "business_address" in (r.body_template or "")
        assert "company_website" in (r.body_template or "")
    db.close()
    engine.dispose()