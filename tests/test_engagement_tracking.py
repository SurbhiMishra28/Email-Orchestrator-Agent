"""Engagement tracking tests: opt-in gating, signed tokens and public endpoints."""
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Contact, Draft, Event, Settings
from app.services import tracking as tracking_service


def _memory_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _draft(db, tenant_id=1, body="Hello\n\nVisit https://example.com/page today."):
    contact = Contact(
        email=f"track-{uuid.uuid4().hex[:8]}@example.com",
        eligible_to_email=True,
        tenant_id=tenant_id,
    )
    db.add(contact)
    db.commit()
    draft = Draft(
        contact_id=contact.id,
        subject="Tracked",
        body=body,
        status="sent",
        tenant_id=tenant_id,
    )
    db.add(draft)
    db.commit()
    return draft


def test_tokens_round_trip_and_reject_tampering():
    token = tracking_service.make_token(11, 3)
    assert tracking_service.parse_token(token) == (11, 3)
    assert tracking_service.parse_token("garbage") is None
    payload, _, signature = token.partition(".")
    assert tracking_service.parse_token(f"{payload}.{'0' * len(signature)}") is None


def test_tracking_is_off_by_default_and_therefore_adds_no_html():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        db.add(Settings(tenant_id=1))
        db.commit()
        assert tracking_service.tracking_enabled(db, 1) is False

        draft = _draft(db)
        assert tracking_service.send_html_for_draft(db, draft, 1) is None
    finally:
        db.close()
        engine.dispose()


def test_enabled_tracking_wraps_links_and_adds_the_pixel():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        db.add(Settings(tenant_id=1, tracking_enabled=True))
        db.commit()

        draft = _draft(db)
        html_body = tracking_service.send_html_for_draft(db, draft, 1)

        assert html_body is not None
        token = tracking_service.make_token(draft.id, 1)
        assert f"/api/track/open/{token}" in html_body
        assert "/api/track/click/" in html_body
        assert "https://example.com/page" in html_body
        assert 'width="1"' in html_body
    finally:
        db.close()
        engine.dispose()


def test_auto_replies_are_never_tracked():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        db.add(Settings(tenant_id=1, tracking_enabled=True))
        db.commit()

        contact = Contact(
            email=f"auto-{uuid.uuid4().hex[:8]}@example.com",
            eligible_to_email=True,
            tenant_id=1,
        )
        db.add(contact)
        db.commit()
        draft = Draft(
            contact_id=contact.id,
            subject="Auto",
            body="Thanks for replying",
            status="sent",
            variables={"message_kind": "auto_reply"},
            tenant_id=1,
        )
        db.add(draft)
        db.commit()

        assert tracking_service.send_html_for_draft(db, draft, 1) is None
    finally:
        db.close()
        engine.dispose()


def test_open_and_click_record_tenant_scoped_events():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        draft = _draft(db)
        token = tracking_service.make_token(draft.id, 1)

        assert tracking_service.record_open(db, token) is True
        target = tracking_service.record_click(db, token, "https://example.com/x")
        assert target == "https://example.com/x"

        events = (
            db.query(Event)
            .filter(Event.tenant_id == 1)
            .order_by(Event.id.asc())
            .all()
        )
        assert [event.event_type for event in events] == [
            "email_opened",
            "link_clicked",
        ]
        assert all((event.data or {}).get("draft_id") == draft.id for event in events)
        assert all(event.contact_id == draft.contact_id for event in events)
    finally:
        db.close()
        engine.dispose()


def test_invalid_token_records_nothing():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        _draft(db)
        assert tracking_service.record_open(db, "not-a-token") is False
        assert tracking_service.record_click(db, "not-a-token", None) is None
        assert db.query(Event).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_click_rejects_non_http_targets():
    engine, session_factory = _memory_db()
    db = session_factory()
    try:
        draft = _draft(db)
        token = tracking_service.make_token(draft.id, 1)
        # A javascript: or relative target must not become the redirect.
        target = tracking_service.record_click(db, token, "javascript:alert(1)")
        assert target.startswith("http")
        assert "javascript" not in target
    finally:
        db.close()
        engine.dispose()


def test_mailer_sends_multipart_alternative_only_when_html_is_given(monkeypatch):
    """The tracked HTML part never replaces the plain-text body."""
    from types import SimpleNamespace

    from app.services import mailer

    captured = []

    class FakeServer:
        def login(self, *_args):
            return None

        def send_message(self, message):
            captured.append(message)

        def quit(self):
            return None

    monkeypatch.setattr(mailer, "_open_server", lambda *a, **k: FakeServer())

    config = SimpleNamespace(
        host="smtp.example.com",
        port=587,
        user="user@example.com",
        password="secret",
        sender="user@example.com",
        configured=True,
    )

    mailer.send_email(config, "lead@example.com", "Hi", "Plain body")

    mailer.send_email(
        config,
        "lead@example.com",
        "Hi",
        "Plain body",
        html_body="<div><p>Plain body</p></div>",
    )

    plain_message, multipart_message = captured
    assert plain_message.get_content_type() == "text/plain"
    assert multipart_message.get_content_type() == "multipart/alternative"
    subtypes = [
        part.get_content_subtype() for part in multipart_message.iter_parts()
    ]
    assert subtypes == ["plain", "html"]
    assert "Plain body" in multipart_message.get_body(("plain",)).get_content()


def test_public_endpoints_are_unauthenticated(client):
    """The pixel and click endpoints work with no bearer token and set no-store."""
    from app.db import Contact, Draft, SessionLocal, Tenant

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
        tenant_id = tenant.id
        contact = Contact(
            email=f"public-{uuid.uuid4().hex[:8]}@example.com",
            eligible_to_email=True,
            tenant_id=tenant_id,
        )
        db.add(contact)
        db.commit()
        draft = Draft(
            contact_id=contact.id,
            subject="Public",
            body="Body",
            status="sent",
            tenant_id=tenant_id,
        )
        db.add(draft)
        db.commit()
        token = tracking_service.make_token(draft.id, tenant_id)
    finally:
        db.close()

    pixel = client.get(f"/api/track/open/{token}", headers={})
    assert pixel.status_code == 200, pixel.text
    assert pixel.headers["content-type"] == "image/gif"
    assert "no-store" in pixel.headers.get("cache-control", "")

    click = client.get(
        f"/api/track/click/{token}",
        params={"url": "https://example.com/landing"},
        headers={},
        follow_redirects=False,
    )
    assert click.status_code == 302
    assert click.headers["location"] == "https://example.com/landing"

    bad = client.get("/api/track/open/not-a-token", headers={})
    assert bad.status_code == 200  # still an image, just records nothing


def test_tracking_settings_toggle_round_trips(client):
    before = client.get("/api/settings")
    assert before.status_code == 200, before.text
    assert before.json()["tracking_enabled"] is False

    enabled = client.post("/api/settings", json={"tracking_enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["tracking_enabled"] is True

    disabled = client.post("/api/settings", json={"tracking_enabled": False})
    assert disabled.json()["tracking_enabled"] is False
