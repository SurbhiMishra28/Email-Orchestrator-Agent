"""The company address must reach the footer, and the follow-up must be full.

A one-line follow-up reads as an accident, and a footer without a postal address
gives the recipient no way to tell who is writing.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agents
from app.db import Base, Settings, Template, Tenant


def _session(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(agents, "SessionLocal", factory)
    db = factory()
    db.add(Tenant(id=1, name="T"))
    db.add(
        Settings(
            tenant_id=1,
            business_name="Acme",
            footer_text="You asked to hear from us.",
            business_address="2nd Floor, Tower B, Noida, UP 201301",
        )
    )
    db.commit()
    return factory, engine


ADDRESS = "2nd Floor, Tower B, Noida, UP 201301"


def test_render_footer_includes_address(monkeypatch):
    factory, engine = _session(monkeypatch)
    db = factory()
    try:
        variables = {
            "footer_text": "You asked to hear from us.",
            "business_address": ADDRESS,
            "sender_name": "Sales",
        }
        rendered = agents._render_footer(None, variables)
        assert "You asked to hear from us." in rendered
        assert ADDRESS in rendered
        # The address must come after the note, not before it.
        assert rendered.index("You asked") < rendered.index(ADDRESS)
    finally:
        db.close()
        engine.dispose()


def test_address_is_not_duplicated_when_already_present(monkeypatch):
    variables = {
        "footer_text": f"Acme Ltd, {ADDRESS}",
        "business_address": ADDRESS,
    }
    rendered = agents._render_footer(None, variables)
    assert rendered.count(ADDRESS) == 1


def test_no_address_leaves_the_footer_unchanged(monkeypatch):
    variables = {"footer_text": "Just a note.", "business_address": ""}
    assert agents._render_footer(None, variables) == "Just a note."


def test_followup_template_is_substantial(monkeypatch):
    """The seeded follow-up must read like a real email, not a stub."""
    from app.services.provisioning import DEFAULT_FOLLOWUP_BODY

    assert len(DEFAULT_FOLLOWUP_BODY) > 400
    assert "Just wanted to follow up on my previous email" not in DEFAULT_FOLLOWUP_BODY
    # The follow-up restates the value and carries the signature block.
    for needle in ("{{ first_name", "calendly_url", "{{ business_name", "{{ business_address", "{{ company_website"):
        assert needle in DEFAULT_FOLLOWUP_BODY, needle


def test_provisioning_upgrades_the_old_followup(monkeypatch):
    from app.services import provisioning

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(Tenant(id=1, name="T"))
    db.add(Settings(tenant_id=1))
    db.add(
        Template(
            tenant_id=1,
            name="Follow-up",
            category="followup",
            subject_template="Following up",
            body_template="Hi {{first_name}},\n\nJust wanted to follow up on my previous email...",
        )
    )
    db.commit()

    provisioning.provision_tenant_defaults(db, tenant_id=1, inherit_environment=False)

    row = (
        db.query(Template)
        .filter(Template.tenant_id == 1, Template.category == "followup")
        .first()
    )
    assert len(row.body_template) > 400
    db.close()
    engine.dispose()