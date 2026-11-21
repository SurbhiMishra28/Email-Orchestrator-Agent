"""A/B testing: variant storage, deterministic assignment and results.

Assignment is a pure function of ``(test_id, contact_id)`` so a contact always
receives the same variant, even across queue passes and restarts. Drafts record
the chosen variant in ``variables`` so results can be recomputed later without
depending on the current test state.
"""
import hashlib
import logging
from typing import Any, Dict, List, Optional

from app.db import ABTest, ABVariant, Contact, Draft, Event

logger = logging.getLogger(__name__)


def _bucket(test_id: int, contact_id: int) -> int:
    digest = hashlib.sha256(f"{test_id}:{contact_id}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def pick_variant(
    variants: List[ABVariant], test_id: int, contact_id: int
) -> Optional[ABVariant]:
    """Choose one variant by weight using a stable hash of the contact id."""
    weighted = [variant for variant in variants if (variant.weight or 0) > 0]
    if not weighted:
        return None
    total = sum(variant.weight for variant in weighted)
    position = _bucket(test_id, contact_id) % total
    for variant in sorted(weighted, key=lambda item: item.id):
        if position < variant.weight:
            return variant
        position -= variant.weight
    return weighted[-1]


def active_test_for_template(
    db, tenant_id: int, template_id: Optional[int]
) -> Optional[ABTest]:
    """The tenant's running experiment for ``template_id``, if any."""
    query = db.query(ABTest).filter(
        ABTest.tenant_id == tenant_id,
        ABTest.status == "active",
    )
    if template_id is not None:
        query = query.filter(ABTest.template_id == template_id)
    return query.order_by(ABTest.id.asc()).first()


def variants_for_test(db, test: ABTest) -> List[ABVariant]:
    return (
        db.query(ABVariant)
        .filter(
            ABVariant.ab_test_id == test.id,
            ABVariant.tenant_id == test.tenant_id,
        )
        .order_by(ABVariant.id.asc())
        .all()
    )


def assignment_for_contact(
    variants: List[ABVariant], test_id: int, contact_id: int
) -> Optional[Dict[str, Any]]:
    """``{test_id, variant}`` for a contact using an already-loaded variant list."""
    variant = pick_variant(variants, test_id, contact_id)
    if not variant:
        return None
    return {"test_id": test_id, "variant": variant}


def variant_for_contact(
    db, tenant_id: int, contact_id: int, template_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Return ``{test_id, variant}`` for a contact, or ``None`` when untested."""
    test = active_test_for_template(db, tenant_id, template_id)
    if not test:
        return None
    return assignment_for_contact(
        variants_for_test(db, test), test.id, contact_id
    )


def apply_variant(draft_variables: Dict[str, Any], assignment: Dict[str, Any]):
    """Merge the chosen variant's ids into a draft's ``variables``."""
    variant = assignment["variant"]
    draft_variables = dict(draft_variables or {})
    draft_variables["ab_test_id"] = assignment["test_id"]
    draft_variables["ab_variant_id"] = variant.id
    draft_variables["ab_variant_label"] = variant.label
    return draft_variables


def test_results(db, test: ABTest) -> Dict[str, Any]:
    """Per-variant sent/opened/clicked/replied counts for one experiment."""
    variants = (
        db.query(ABVariant)
        .filter(
            ABVariant.ab_test_id == test.id,
            ABVariant.tenant_id == test.tenant_id,
        )
        .order_by(ABVariant.id.asc())
        .all()
    )
    variant_ids = {variant.id for variant in variants}

    sent_drafts: List[Draft] = []
    for draft in (
        db.query(Draft)
        .filter(Draft.tenant_id == test.tenant_id, Draft.status == "sent")
        .all()
    ):
        variant_id = (draft.variables or {}).get("ab_variant_id")
        if variant_id in variant_ids:
            sent_drafts.append(draft)

    opened = {
        (event.data or {}).get("draft_id")
        for event in db.query(Event)
        .filter(
            Event.tenant_id == test.tenant_id,
            Event.event_type == "email_opened",
        )
        .all()
    }
    clicked = {
        (event.data or {}).get("draft_id")
        for event in db.query(Event)
        .filter(
            Event.tenant_id == test.tenant_id,
            Event.event_type == "link_clicked",
        )
        .all()
    }
    replied_contacts = {
        event.contact_id
        for event in db.query(Event)
        .filter(
            Event.tenant_id == test.tenant_id,
            Event.event_type == "reply_received",
        )
        .all()
    }

    buckets: Dict[int, Dict[str, Any]] = {
        variant.id: {
            "variant_id": variant.id,
            "label": variant.label,
            "subject": variant.subject,
            "weight": variant.weight,
            "sent": 0,
            "opened": 0,
            "clicked": 0,
            "replied": 0,
        }
        for variant in variants
    }

    for draft in sent_drafts:
        variant_id = (draft.variables or {}).get("ab_variant_id")
        bucket = buckets.get(variant_id)
        if not bucket:
            continue
        bucket["sent"] += 1
        if draft.id in opened:
            bucket["opened"] += 1
        if draft.id in clicked:
            bucket["clicked"] += 1
        if draft.contact_id in replied_contacts:
            bucket["replied"] += 1

    for bucket in buckets.values():
        sent = bucket["sent"]
        bucket["reply_rate"] = round(bucket["replied"] / sent * 100, 1) if sent else 0.0
        bucket["open_rate"] = round(bucket["opened"] / sent * 100, 1) if sent else 0.0

    return {
        "test_id": test.id,
        "name": test.name,
        "status": test.status,
        "variants": list(buckets.values()),
    }


def results_for_tenant(db, tenant_id: int) -> List[Dict[str, Any]]:
    tests = (
        db.query(ABTest)
        .filter(ABTest.tenant_id == tenant_id)
        .order_by(ABTest.id.desc())
        .all()
    )
    return [test_results(db, test) for test in tests]


def contact_exists(db, tenant_id: int, contact_id: int) -> bool:
    return (
        db.query(Contact.id)
        .filter(Contact.id == contact_id, Contact.tenant_id == tenant_id)
        .first()
        is not None
    )
