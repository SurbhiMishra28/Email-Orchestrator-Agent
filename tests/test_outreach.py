"""Automatic intro drafting: one draft per eligible contact, never twice."""
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.agents
from app.db import Base, Contact, Draft, Log, Template
from app.services import outreach


@pytest.fixture
def outreach_db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(outreach, "SessionLocal", session_factory)
    monkeypatch.setattr(app.agents, "SessionLocal", session_factory)

    async def expand_template(template, contact):
        return {"subject": f"Hello {contact.name}", "body": "Intro body"}

    monkeypatch.setattr(app.agents, "expand_template_with_ai", expand_template)
    try:
        yield session_factory
    finally:
        engine.dispose()


def _seed(session_factory, tenant_id=1, prefix=""):
    db = session_factory()
    db.add(
        Template(
            tenant_id=tenant_id,
            name="Intro Email",
            category="intro",
            subject_template="Hi {{first_name}}",
            body_template="Intro",
            is_active=True,
        )
    )
    db.add_all(
        [
            Contact(tenant_id=tenant_id, email=f"{prefix}a@example.com", name="Ann", eligible_to_email=True),
            Contact(tenant_id=tenant_id, email=f"{prefix}b@example.com", name="Bob", eligible_to_email=True),
            Contact(tenant_id=tenant_id, email=f"{prefix}c@example.com", name="Cal", eligible_to_email=False),
        ]
    )
    db.commit()
    db.close()


def test_intro_drafts_are_created_once_per_eligible_contact(outreach_db):
    _seed(outreach_db)

    first = asyncio.run(outreach.create_intro_drafts(tenant_id=1))
    assert first["created"] == 2
    assert first["skipped"] == 0

    second = asyncio.run(outreach.create_intro_drafts(tenant_id=1))
    assert second["created"] == 0
    assert second["skipped"] == 2

    db = outreach_db()
    try:
        drafts = db.query(Draft).all()
        assert len(drafts) == 2
        assert {draft.variables["campaign_type"] for draft in drafts} == {"intro"}
        assert {draft.status for draft in drafts} == {"draft"}
        assert all(draft.tenant_id == 1 for draft in drafts)
    finally:
        db.close()


def test_intro_drafts_never_cross_tenants(outreach_db):
    _seed(outreach_db, tenant_id=1)
    _seed(outreach_db, tenant_id=2, prefix="two-")

    result = asyncio.run(outreach.create_intro_drafts(tenant_id=2))

    assert result["created"] == 2
    db = outreach_db()
    try:
        assert {draft.tenant_id for draft in db.query(Draft).all()} == {2}
    finally:
        db.close()


def test_missing_intro_template_creates_nothing_and_logs(outreach_db):
    db = outreach_db()
    db.add(
        Contact(email="a@example.com", name="Ann", eligible_to_email=True)
    )
    db.commit()
    db.close()

    result = asyncio.run(outreach.create_intro_drafts(tenant_id=1))

    assert result["created"] == 0
    assert result["reason"] == "no intro template"
    db = outreach_db()
    try:
        assert db.query(Draft).count() == 0
        assert "no active intro template" in db.query(Log).one().message
    finally:
        db.close()


def test_import_hook_stays_opt_in(outreach_db):
    db = outreach_db()
    from app.db import Settings

    db.add(
        Template(
            tenant_id=1,
            name="Intro",
            category="intro",
            subject_template="Hi",
            body_template="Intro",
            is_active=True,
        )
    )
    db.add(Settings(tenant_id=1, AUTOPILOT=False, AUTO_APPROVE=False))
    db.add(Contact(tenant_id=1, email="a@example.com", name="Ann", eligible_to_email=True))
    db.commit()
    db.close()

    result = asyncio.run(
        outreach.create_intro_drafts(tenant_id=1, require_automation=True)
    )

    assert result["created"] == 0
    assert result["reason"] == "automation disabled"
