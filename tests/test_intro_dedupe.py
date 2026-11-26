"""One intro draft per contact, even when invocations race.

Duplicates mean the same person is mailed twice, so the dedupe must keep the
oldest unsent draft and drop the rest without touching what already went out.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Settings, Tenant
from app.services.outreach import dedupe_intro_drafts


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    db.add(Tenant(id=1, name="T"))
    db.add(Settings(tenant_id=1))
    c1 = Contact(email="a@skorainfotech.com", eligible_to_email=True, tenant_id=1)
    c2 = Contact(email="b@skorainfotech.com", eligible_to_email=True, tenant_id=1)
    db.add_all([c1, c2])
    db.flush()

    def draft(contact, status, campaign_type="intro", followup_for=None):
        variables = {"campaign_type": campaign_type}
        if followup_for:
            variables["followup_for"] = followup_for
        return Draft(contact_id=contact.id, subject="s", body="b",
                     status=status, tenant_id=1, variables=variables)

    # c1: two unsent intros (a race) -> keep the first, drop the second.
    db.add_all([draft(c1, "draft"), draft(c1, "draft")])
    # c2: one sent intro (must survive, and is not in scope) + two unsent.
    db.add_all([draft(c2, "sent"), draft(c2, "draft"), draft(c2, "draft")])
    # A follow-up draft must never be treated as an intro.
    db.add(draft(c2, "draft", campaign_type="followup", followup_for=99))
    db.commit()
    return db, engine, c1, c2


def test_dedupe_keeps_one_unsent_intro_per_contact():
    db, engine, c1, c2 = _session()
    try:
        # c1 has one duplicate, c2 has one -> two removals.
        removed = dedupe_intro_drafts(db, 1)
        assert removed == 2

        rows = db.query(Draft).filter(Draft.tenant_id == 1).all()
        intros = [d for d in rows if (d.variables or {}).get("campaign_type") == "intro"]
        by_contact = {}
        for d in intros:
            by_contact.setdefault(d.contact_id, []).append(d)

        # One *unsent* intro per contact; the sent one is untouched.
        assert len([d for d in by_contact[c1.id] if d.status != "sent"]) == 1
        assert len([d for d in by_contact[c2.id] if d.status != "sent"]) == 1
        assert any(d.status == "sent" for d in by_contact[c2.id])

        # The follow-up draft survived.
        assert any((d.variables or {}).get("followup_for") == 99 for d in rows)
    finally:
        db.close()
        engine.dispose()


def test_dedupe_is_idempotent():
    db, engine, _, _ = _session()
    try:
        assert dedupe_intro_drafts(db, 1) == 2
        assert dedupe_intro_drafts(db, 1) == 0
    finally:
        db.close()
        engine.dispose()