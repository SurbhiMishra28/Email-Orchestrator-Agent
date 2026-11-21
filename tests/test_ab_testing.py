"""A/B testing tests: variant storage, deterministic assignment, results."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import ABTest, ABVariant, Base, Contact, Draft, Event
from app.services.abtesting import (
    active_test_for_template,
    assignment_for_contact,
    pick_variant,
    test_results as compute_results,
    variants_for_test,
)


def _memory_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _variants(db, test_id, tenant_id=1, weights=(1, 1)):
    rows = []
    for index, weight in enumerate(weights):
        variant = ABVariant(
            tenant_id=tenant_id,
            ab_test_id=test_id,
            label=f"v{index}",
            subject=f"Subject {index}",
            body=f"Body {index}",
            weight=weight,
        )
        db.add(variant)
        rows.append(variant)
    db.commit()
    return rows


def test_assignment_is_deterministic_per_contact():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        variants = _variants(db, test_id=1)
        first = pick_variant(variants, 1, 4242).id
        for _ in range(5):
            assert pick_variant(variants, 1, 4242).id == first
    finally:
        db.close()
        engine.dispose()


def test_assignment_respects_weights():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        variants = _variants(db, test_id=2, weights=(9, 1))
        heavy = variants[0].id
        hits = sum(
            1
            for contact_id in range(400)
            if pick_variant(variants, 2, contact_id).id == heavy
        )
        # 9:1 should land near 360/400; allow a wide margin for hash variance.
        assert 280 < hits < 400
    finally:
        db.close()
        engine.dispose()


def test_zero_weight_variant_is_never_selected():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        variants = _variants(db, test_id=3, weights=(0, 5))
        zero_weight = variants[0].id
        for contact_id in range(60):
            assert pick_variant(variants, 3, contact_id).id != zero_weight
    finally:
        db.close()
        engine.dispose()


def test_active_test_lookup_is_tenant_scoped():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        db.add(
            ABTest(tenant_id=1, name="Alpha test", status="active", template_id=7)
        )
        db.add(
            ABTest(tenant_id=2, name="Beta test", status="active", template_id=7)
        )
        db.commit()

        alpha = active_test_for_template(db, 1, 7)
        beta = active_test_for_template(db, 2, 7)
        assert alpha is not None and beta is not None
        assert alpha.tenant_id == 1
        assert beta.tenant_id == 2

        assert active_test_for_template(db, 1, 999) is None
    finally:
        db.close()
        engine.dispose()


def test_paused_tests_are_not_used_for_assignment():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        test = ABTest(tenant_id=1, name="Paused", status="paused")
        db.add(test)
        db.commit()
        _variants(db, test.id)

        assert active_test_for_template(db, 1, None) is None
    finally:
        db.close()
        engine.dispose()


def test_results_count_sent_opened_clicked_and_replied_per_variant():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        test = ABTest(tenant_id=1, name="Results", status="active")
        db.add(test)
        db.commit()
        variants = _variants(db, test.id)

        contact = Contact(
            email=f"ab-{uuid.uuid4().hex[:8]}@example.com",
            eligible_to_email=True,
            tenant_id=1,
        )
        db.add(contact)
        db.commit()

        sent = Draft(
            contact_id=contact.id,
            subject="AB",
            body="Body",
            status="sent",
            sent_at=datetime.now(timezone.utc),
            variables={"ab_test_id": test.id, "ab_variant_id": variants[0].id},
            tenant_id=1,
        )
        pending = Draft(
            contact_id=contact.id,
            subject="AB pending",
            body="Body",
            status="draft",
            variables={"ab_test_id": test.id, "ab_variant_id": variants[0].id},
            tenant_id=1,
        )
        db.add_all([sent, pending])
        db.commit()

        db.add_all(
            [
                Event(
                    tenant_id=1,
                    contact_id=contact.id,
                    event_type="email_opened",
                    data={"draft_id": sent.id},
                ),
                Event(
                    tenant_id=1,
                    contact_id=contact.id,
                    event_type="link_clicked",
                    data={"draft_id": sent.id},
                ),
                Event(
                    tenant_id=1,
                    contact_id=contact.id,
                    event_type="reply_received",
                    data={"sender_email": contact.email},
                ),
            ]
        )
        db.commit()

        results = compute_results(db, test)
        by_label = {bucket["label"]: bucket for bucket in results["variants"]}

        assert by_label["v0"]["sent"] == 1
        assert by_label["v0"]["opened"] == 1
        assert by_label["v0"]["clicked"] == 1
        assert by_label["v0"]["replied"] == 1
        assert by_label["v0"]["reply_rate"] == 100.0
        assert by_label["v1"]["sent"] == 0
        assert by_label["v1"]["reply_rate"] == 0.0
    finally:
        db.close()
        engine.dispose()


def _fresh_headers(client):
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/auth/register",
        json={
            "email": f"ab-{suffix}@example.com",
            "password": "ab-password-123",
            "name": "AB User",
            "tenant_name": f"AB Tenant {suffix}",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def _template(client, headers):
    templates = client.get("/api/templates", headers=headers)
    assert templates.status_code == 200, templates.text
    return templates.json()["templates"][0]["id"]


def test_ab_test_crud_over_the_api(client):
    headers = _fresh_headers(client)
    template_id = _template(client, headers)

    created = client.post(
        "/api/ab-tests",
        json={
            "name": "Subject line test",
            "template_id": template_id,
            "variants": [
                {"label": "short", "subject": "Quick question", "body": "Hi"},
                {"label": "long", "subject": "A longer subject line", "body": "Hello"},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    test_id = created.json()["id"]
    assert len(created.json()["variants"]) == 2

    listed = client.get("/api/ab-tests", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [test_id]

    fetched = client.get(f"/api/ab-tests/{test_id}", headers=headers)
    assert fetched.json()["name"] == "Subject line test"

    paused = client.patch(
        f"/api/ab-tests/{test_id}", json={"status": "paused"}, headers=headers
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    bad_status = client.patch(
        f"/api/ab-tests/{test_id}", json={"status": "nope"}, headers=headers
    )
    assert bad_status.status_code == 422

    results = client.get(f"/api/ab-tests/{test_id}/results", headers=headers)
    assert results.status_code == 200, results.text
    assert {bucket["sent"] for bucket in results.json()["variants"]} == {0}

    deleted = client.delete(f"/api/ab-tests/{test_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/ab-tests/{test_id}", headers=headers).status_code == 404


def test_ab_test_rejects_duplicate_labels(client):
    headers = _fresh_headers(client)
    response = client.post(
        "/api/ab-tests",
        json={
            "name": "Dupes",
            "variants": [
                {"label": "same", "subject": "A", "body": "A"},
                {"label": "same", "subject": "B", "body": "B"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 409


def test_ab_test_rejects_all_zero_weights(client):
    headers = _fresh_headers(client)
    response = client.post(
        "/api/ab-tests",
        json={
            "name": "Zero",
            "variants": [{"label": "a", "subject": "A", "body": "A", "weight": 0}],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_variant_endpoints_enforce_membership(client):
    headers = _fresh_headers(client)
    created = client.post(
        "/api/ab-tests",
        json={
            "name": "Variants",
            "variants": [{"label": "only", "subject": "A", "body": "A"}],
        },
        headers=headers,
    )
    test_id = created.json()["id"]
    variant_id = created.json()["variants"][0]["id"]

    added = client.post(
        f"/api/ab-tests/{test_id}/variants",
        json={"label": "second", "subject": "B", "body": "B"},
        headers=headers,
    )
    assert added.status_code == 201, added.text

    duplicate = client.post(
        f"/api/ab-tests/{test_id}/variants",
        json={"label": "second", "subject": "C", "body": "C"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/ab-tests/{test_id}/variants/{variant_id}",
        json={"subject": "Updated"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["subject"] == "Updated"

    removed = client.delete(
        f"/api/ab-tests/{test_id}/variants/{variant_id}", headers=headers
    )
    assert removed.status_code == 204

    # One variant must remain, so removing the last one is a conflict.
    last_id = added.json()["id"]
    blocked = client.delete(
        f"/api/ab-tests/{test_id}/variants/{last_id}", headers=headers
    )
    assert blocked.status_code == 409


def test_ab_tests_are_tenant_isolated(client):
    alpha = _fresh_headers(client)
    beta = _fresh_headers(client)

    created = client.post(
        "/api/ab-tests",
        json={
            "name": "Alpha only",
            "variants": [{"label": "a", "subject": "A", "body": "A"}],
        },
        headers=alpha,
    )
    test_id = created.json()["id"]

    assert client.get("/api/ab-tests", headers=beta).json() == []
    assert client.get(f"/api/ab-tests/{test_id}", headers=beta).status_code == 404
    assert (
        client.get(f"/api/ab-tests/{test_id}/results", headers=beta).status_code == 404
    )
    assert client.delete(f"/api/ab-tests/{test_id}", headers=beta).status_code == 404


def test_run_all_assigns_the_selected_variant(client):
    """`run-all` records the experiment and variant on each created draft."""
    from app.db import Draft, SessionLocal

    headers = _fresh_headers(client)
    template_id = _template(client, headers)

    created = client.post(
        "/api/ab-tests",
        json={
            "name": "Run-all test",
            "template_id": template_id,
            "variants": [
                {"label": "control", "subject": "Control subject", "body": "Control"},
                {"label": "challenger", "subject": "Challenger", "body": "Challenger"},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    test_id = created.json()["id"]
    label_to_id = {item["label"]: item["id"] for item in created.json()["variants"]}

    contact = client.post(
        "/api/contacts",
        json={
            "email": f"ab-run-{uuid.uuid4().hex[:8]}@example.com",
            "eligible_to_email": True,
        },
        headers=headers,
    )
    assert contact.status_code == 200, contact.text
    contact_id = contact.json()["id"]

    run = client.post(
        "/api/queue/run-all",
        json={"template_id": template_id, "contact_ids": [contact_id]},
        headers=headers,
    )
    assert run.status_code == 200, run.text
    assert run.json()["drafts_created"] == 1

    db = SessionLocal()
    try:
        draft = (
            db.query(Draft)
            .filter(Draft.contact_id == contact_id)
            .order_by(Draft.id.desc())
            .first()
        )
        assert draft.variables["ab_test_id"] == test_id
        assert draft.variables["ab_variant_id"] in label_to_id.values()
        assert draft.variables["ab_variant_label"] in label_to_id
        assert draft.subject in {"Control subject", "Challenger"}
    finally:
        db.close()
